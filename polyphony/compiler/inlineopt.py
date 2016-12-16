from collections import defaultdict, deque
from .scope import Scope
from .block import Block
from .irvisitor import IRVisitor
from .ir import *
from .env import env
from .type import Type
from .varreplacer import VarReplacer
from .copyopt import CopyOpt
import logging
logger = logging.getLogger()

class InlineOpt:
    def __init__(self):
        pass

    def process_all(self):
        self.dones = set()
        self.inline_counts = defaultdict(int)
        for scope in env.call_graph.bfs_ordered_nodes():
            if scope not in self.dones:
                self._process_scope(scope)

        using_scopes = self.collect_using_scopes()

        scopes = Scope.get_scopes(bottom_up=False, contain_class=True)
        return set(scopes).difference(using_scopes)

    def collect_using_scopes(self):
        calls = defaultdict(list)
        collector = CallCollector(calls)
        using_scopes = set()
        scopes = Scope.get_scopes(bottom_up=False, contain_class=True)
        for s in scopes:
            if s.is_testbench() or s.is_global() or s.is_class():
                using_scopes.add(s)
            collector.process(s)

        for callee, _ in calls.items():
            using_scopes.add(callee)
        return using_scopes

    def _process_scope(self, scope):
        calls = defaultdict(list)
        collector = CallCollector(calls)
        collector.process(scope)
        for callee, calls in calls.items():
            self._process_scope(callee)
            if callee.is_method():
                self._process_method(callee, scope, calls)
            else:
                self._process_func(callee, scope, calls)
        self.dones.add(scope)
        if calls:
            self._reduce_useless_move(scope)

    def _process_func(self, callee, caller, calls):
        if caller.is_testbench() or caller.is_global():
            return
        for call, call_stm in calls:
            self.inline_counts[caller] += 1
            assert callee is call.func_scope

            symbol_map = self._make_replace_symbol_map(call, caller, callee, str(self.inline_counts[caller]))
            result_sym = symbol_map[callee.symbols[Symbol.return_prefix]]
            result_sym.name = callee.orig_name + '_result' + str(self.inline_counts[caller])

            block_map = callee.clone_blocks(caller)
            callee_entry_blk = block_map[callee.entry_block]
            callee_exit_blk = block_map[callee.exit_block]
            assert len(callee_exit_blk.succs) <= 1

            result = TEMP(result_sym, Ctx.LOAD)
            result.lineno = call_stm.lineno
            if call_stm.is_a(MOVE):
                assert call_stm.src is call
                call_stm.src = result
            elif call_stm.is_a(EXPR):
                assert call_stm.exp is call
                call_stm.exp = result

            sym_replacer = SymbolReplacer(symbol_map)
            sym_replacer.process(caller, callee_entry_blk)

            self._merge_blocks(call_stm, callee_entry_blk, callee_exit_blk)

    def _process_method(self, callee, caller, calls):
        if caller.is_testbench() or caller.is_global():
            return
        for call, call_stm in calls:
            self.inline_counts[caller] += 1

            symbol_map = self._make_replace_symbol_map(call, caller, callee, str(self.inline_counts[caller]))
            result_sym = symbol_map[callee.symbols[Symbol.return_prefix]]
            result_sym.name = callee.orig_name + '_result' + str(self.inline_counts[caller])

            block_map = callee.clone_blocks(caller)
            callee_entry_blk = block_map[callee.entry_block]
            callee_exit_blk = block_map[callee.exit_block]
            assert len(callee_exit_blk.succs) <= 1

            if not callee.is_ctor():
                result = TEMP(result_sym, Ctx.LOAD)
                result.lineno = call_stm.lineno
                if call_stm.is_a(MOVE):
                    assert call_stm.src is call
                    call_stm.src = result
                elif call_stm.is_a(EXPR):
                    assert call_stm.exp is call
                    call_stm.exp = result

            attr_map = {}
            if caller.is_method() and caller.parent is not callee.parent:
                if callee.is_ctor():
                    if call_stm.is_a(MOVE):
                        attr_map[callee.symbols[env.self_name]] = call_stm.dst
                else:
                    if call_stm.is_a(MOVE):
                        object_sym = call.func.exp.qualified_symbol()
                    elif call_stm.is_a(EXPR):
                        object_sym = call.func.exp.qualified_symbol()
                    symbol_map[callee.symbols[env.self_name]] = object_sym
            else:
                if callee.is_ctor():
                    if call_stm.is_a(MOVE):
                        assert call_stm.src is call
                        object_sym = call_stm.dst.qualified_symbol()
                    else:
                        assert False
                else:
                    object_sym = call.func.exp.qualified_symbol()
                symbol_map[callee.symbols[env.self_name]] = object_sym

            sym_replacer = SymbolReplacer(symbol_map, attr_map)
            sym_replacer.process(caller, callee_entry_blk)

            self._merge_blocks(call_stm, callee_entry_blk, callee_exit_blk)

            if callee.is_ctor():
                assert call_stm.src is call
                call_stm.block.stms.remove(call_stm)


    def _make_replace_symbol_map(self, call, caller, callee, inline_id):
        symbol_map = callee.clone_symbols(caller, postfix='_inl' + inline_id)
        if callee.is_method():
            params = callee.params[1:]
        else:
            params = callee.params[:]
        for i, (p, copy, defval) in enumerate(params):
            if len(call.args) > i:
                arg = call.args[i]
            else:
                arg = defval
            if arg.is_a(TEMP):
                symbol_map[p] = arg.sym
                symbol_map[copy] = arg.sym
            elif arg.is_a(CONST):
                symbol_map[p] = arg
            elif arg.is_a(ATTR):
                assert False # TODO
            else:
                assert False
        return symbol_map


    def _merge_blocks(self, call_stm, callee_entry_blk, callee_exit_blk):
        caller_scope = call_stm.block.scope
        early_call_blk = call_stm.block
        late_call_blk  = Block(caller_scope)
        late_call_blk.succs = early_call_blk.succs
        for succ in late_call_blk.succs:
            succ.replace_pred(early_call_blk, late_call_blk)

        idx = early_call_blk.stms.index(call_stm)
        late_call_blk.stms = early_call_blk.stms[idx:]
        for s in late_call_blk.stms:
            s.block = late_call_blk
        early_call_blk.stms = early_call_blk.stms[:idx]
        early_call_blk.append_stm(JUMP(callee_entry_blk))
        early_call_blk.succs = [callee_entry_blk]
        callee_entry_blk.preds = [early_call_blk]

        if callee_exit_blk.stms and callee_exit_blk.stms[-1].is_a(RET):
            callee_exit_blk.stms.pop()
        callee_exit_blk.append_stm(JUMP(late_call_blk))
        callee_exit_blk.succs = [late_call_blk]
        late_call_blk.preds = [callee_exit_blk]

        if caller_scope.exit_block is early_call_blk:
            caller_scope.exit_block = late_call_blk

    def _reduce_useless_move(self, scope):
        for block in scope.traverse_blocks():
            removes = []
            for stm in block.stms:
                if stm.is_a(MOVE) and stm.dst.is_a(TEMP) and stm.src.is_a(TEMP) and stm.dst.sym is stm.src.sym:
                    removes.append(stm)
            for rm in removes:
                block.stms.remove(rm)


class CallCollector(IRVisitor):
    def __init__(self, calls):
        super().__init__()
        self.calls = calls

    def visit_CALL(self, ir):
        self.calls[ir.func_scope].append((ir, self.current_stm))

    def visit_NEW(self, ir):
        assert ir.func_scope.is_class()
        ctor = ir.func_scope.find_ctor()
        assert ctor
        self.calls[ctor].append((ir, self.current_stm))


class SymbolReplacer(IRVisitor):
    def __init__(self, sym_map, attr_map = None, inst_name = None):
        super().__init__()
        self.sym_map = sym_map
        self.attr_map = attr_map
        self.inst_name = inst_name

    def traverse_blocks(self, entry_block, full=False, longitude=False):
        assert len(entry_block.preds) == 0
        visited = set()
        yield from entry_block.traverse(visited, full=False, longitude=False)

    def process(self, scope, entry_block):
        self.scope = scope
        for blk in self.traverse_blocks(entry_block):
            self._process_block(blk)

    def _qsym_to_var(self, qsym, ctx):
        if len(qsym) == 1:
            return TEMP(qsym[0], ctx)
        else:
            exp = self._qsym_to_var(qsym[:-1], Ctx.LOAD)
            return ATTR(exp, qsym[-1], ctx)

    def visit_TEMP(self, ir):
        if self.attr_map and ir.sym in self.attr_map:
            attr = self.attr_map[ir.sym].clone()
            return attr
        if ir.sym in self.sym_map:
            rep = self.sym_map[ir.sym]
            if isinstance(rep, Symbol):
                ir.sym = rep
                return ir
            elif isinstance(rep, tuple): # qualified_symbol
                var = self._qsym_to_var(rep, ir.ctx)
                var.lineno = ir.lineno
                return var
            else:
                self.current_stm.replace(ir, rep)
                return rep

    def visit_ATTR(self, ir):
        exp = self.visit(ir.exp)
        if exp:
            ir.exp = exp

        if ir.attr in self.sym_map:
            ir.attr = self.sym_map[ir.attr]


class AliasReplacer(CopyOpt):
    def _new_collector(self, copies):
        return AliasDefCollector(copies)

    def __init__(self):
        super().__init__()

    def _find_old_use(self, ir, qsym):
        vars = []
        def find_vars_rec(ir, qsym, vars):
            if isinstance(ir, IR):
                if ir.is_a(ATTR):
                    if Type.is_object(ir.attr.typ):
                        if ir.qualified_symbol() == qsym:
                            vars.append(ir)
                    elif ir.exp.qualified_symbol() == qsym:
                        vars.append(ir.exp)
                else:
                    for k, v in ir.__dict__.items():
                        find_vars_rec(v, qsym, vars)
            elif isinstance(ir, list) or isinstance(ir, tuple):
                for elm in ir:
                    find_vars_rec(elm, qsym, vars)
        find_vars_rec(ir, qsym, vars)
        return vars


class AliasDefCollector(IRVisitor):
    def __init__(self, copies):
        self.copies = copies

    def _is_alias_def(self, mov):
        if not mov.is_a(MOVE):
            return False
        if not mov.src.is_a([TEMP, ATTR]):
            return False
        if not Type.is_object(mov.src.symbol().typ):
            return False
        if not mov.dst.is_a([TEMP, ATTR]):
            return False
        if not Type.is_object(mov.dst.symbol().typ):
            return False
        return True

    def visit_MOVE(self, ir):
        if not self._is_alias_def(ir):
            return
        self.copies.append(ir)

class FlattenFieldAccess(IRVisitor):
    def make_flatname(self, ir):
        assert ir.is_a(ATTR)
        def make_flatname_rec(ir):
            assert ir.is_a(ATTR)
            if ir.exp.is_a(TEMP):
                if ir.exp.sym.name == env.self_name:
                    return ''
                else:
                    return ir.exp.sym.name
            else:
                name1 = make_flatname_rec(ir.exp)
                if name1:
                    flatname = '{}_{}'.format(name1, ir.exp.attr.name)
                else:
                    flatname = ir.exp.attr.name
            return flatname
        flatname = make_flatname_rec(ir)
        if flatname:
            return flatname + '_' + ir.attr.name
        else:
            return ir.attr.name

    def visit_ATTR(self, ir):
        # don't flatten use of the other instance in the class
        if self.scope.is_method():
            return
        # don't flatten use of the static class field
        if Type.is_class(ir.head().typ):
            return
        flatname = self.make_flatname(ir)
        flatsym = self.scope.gen_sym(flatname)
        flatsym.typ = ir.attr.typ
        flatsym.ancestor = ir.attr
        newtemp = TEMP(flatsym, ir.ctx)
        newtemp.lineno = ir.lineno
        self.current_stm.replace(ir, newtemp)

    def visit_CALL(self, ir):
        # we don't flatten a method call
        return

import pdb

class ObjectHierarchyCopier:
    def __init__(self):
        pass

    def _is_object(self, ir):
        return ir.is_a([TEMP, ATTR]) and Type.is_object(ir.symbol().typ)

    def _is_object_copy(self, mov):
        return self._is_object(mov.src) and self._is_object(mov.dst)

    def _collect_object_copy(self, scope):
        copies = []
        for block in scope.traverse_blocks():
            moves = [stm for stm in block.stms if stm.is_a(MOVE)]
            copies.extend([stm for stm in moves if self._is_object_copy(stm)])
        return copies

    def process(self, scope):
        copies = self._collect_object_copy(scope)
        worklist = deque()
        worklist.extend(copies)
        while worklist:
            cp = worklist.popleft()
            class_scope = Type.extra(cp.src.symbol().typ)
            assert class_scope is Type.extra(cp.dst.symbol().typ)
            for sym in class_scope.class_fields.keys():
                if not Type.is_object(sym.typ):
                    continue
                new_dst = ATTR(cp.dst.clone(), sym, Ctx.STORE)
                new_src = ATTR(cp.src.clone(), sym, Ctx.LOAD)
                new_cp = MOVE(new_dst, new_src)
                new_dst.lineno = cp.lineno
                new_src.lineno = cp.lineno
                new_cp.lineno = cp.lineno
                cp_idx = cp.block.stms.index(cp)
                cp.block.insert_stm(cp_idx+1, new_cp)
                if Type.is_object(sym.typ):
                    worklist.append(new_cp)
