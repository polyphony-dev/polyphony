from collections import defaultdict
from .scope import Scope
from .block import Block
from .irvisitor import IRVisitor
from .ir import *
from .env import env
import logging
logger = logging.getLogger()

class InlineOpt:
    def __init__(self):
        pass

    def process_all(self):
        funcalls = defaultdict(set)
        methodcalls = defaultdict(set)
        collector = CallCollector(funcalls, methodcalls)
        for s in Scope.get_scopes(bottom_up=False):
            collector.process(s)
        self._process_func(funcalls)
        self._process_method(methodcalls)

        return self.collect_unused_scopes()

    def collect_unused_scopes(self):
        funcalls = defaultdict(set)
        methodcalls = defaultdict(set)
        collector = CallCollector(funcalls, methodcalls)
        using_scopes = set()
        scopes = Scope.get_scopes(bottom_up=False, contain_class=True)
        for s in scopes:
            if s.is_testbench() or s.is_global() or s.is_class():
                using_scopes.add(s)
            collector.process(s)

        for (_, callee), _ in funcalls.items():
            using_scopes.add(callee)
        for (_, callee), _ in methodcalls.items():
            using_scopes.add(callee)

        return set(scopes).difference(using_scopes)

    def _process_func(self, funcalls):
        new_scopes = []
        inline_count = 0
        items = [(caller, callee, calls) for (caller, callee), calls in reversed(sorted(funcalls.items()))]
        for caller, callee, calls in items:
            # We do not inlining the callee functions of a testbench
            if caller.is_testbench():
                continue
            for call, call_stm in calls:
                inline_count += 1
                assert callee is call.func_scope

                symbol_map = self._make_replace_symbol_map(call, caller, callee, str(inline_count))
                result_sym = symbol_map[callee.symbols[Symbol.return_prefix]]
                result_sym.name = callee.orig_name + '_result' + str(inline_count)

                block_map = callee.clone_blocks(caller)
                callee_root_blk = block_map[callee.root_block]
                callee_leaf_blk = block_map[callee.leaf_block]
                assert len(callee_leaf_blk.succs) <= 1

                if call_stm.is_a(MOVE):
                    assert call_stm.src is call
                    call_stm.src = TEMP(result_sym, Ctx.LOAD)
                elif call_stm.is_a(EXPR):
                    assert call_stm.exp is call
                    call_stm.exp = TEMP(result_sym, Ctx.LOAD)

                sym_replacer = SymbolReplacer(symbol_map)
                sym_replacer.process(caller, callee_root_blk)

                self._merge_blocks(call_stm, callee_root_blk, callee_leaf_blk)


    def _process_method(self, methodcalls):
        new_scopes = []
        inline_count = 0
        items = [(caller, callee, calls) for (caller, callee), calls in reversed(sorted(methodcalls.items()))]
        for caller, callee, calls in items:
            # We do not inlining the callee functions of a testbench
            if caller.is_testbench():
                continue
            for call, call_stm in calls:
                inline_count += 1
                
                symbol_map = self._make_replace_symbol_map(call, caller, callee, str(inline_count))
                result_sym = symbol_map[callee.symbols[Symbol.return_prefix]]
                result_sym.name = callee.orig_name + '_result' + str(inline_count)

                block_map = callee.clone_blocks(caller)
                callee_root_blk = block_map[callee.root_block]
                callee_leaf_blk = block_map[callee.leaf_block]
                assert len(callee_leaf_blk.succs) <= 1
                
                if callee.is_ctor():
                    if call_stm.is_a(MOVE):
                        assert call_stm.src is call
                        object_sym = call_stm.dst.symbol()
                    else:
                        assert False
                elif callee.is_method():
                    if call_stm.is_a(MOVE):
                        assert call_stm.src is call
                        call_stm.src = TEMP(result_sym, Ctx.LOAD)
                    elif call_stm.is_a(EXPR):
                        assert call_stm.exp is call
                        call_stm.exp = TEMP(result_sym, Ctx.LOAD)
                    object_sym = call.func.head()

                sym_replacer = SymbolReplacer(symbol_map, inst_name = object_sym.name)
                sym_replacer.process(caller, callee_root_blk)

                self._merge_blocks(call_stm, callee_root_blk, callee_leaf_blk)
                
                flatten = FlattenFieldAccess()
                flatten.process(caller)

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
            elif arg.is_a(CONST):
                symbol_map[p] = arg
            elif arg.is_a(ATTR):
                assert False # TODO
            else:
                assert False
        return symbol_map


    def _merge_blocks(self, call_stm, callee_root_blk, callee_leaf_blk):
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
        if early_call_blk.stms:
            early_call_blk.append_stm(JUMP(callee_root_blk))
            early_call_blk.succs = [callee_root_blk]
            callee_root_blk.preds = [early_call_blk]
        else:
            if caller_scope.root_block is early_call_blk:
                caller_scope.root_block = callee_root_blk
            else:
                for pred in early_call_blk.preds:
                    pred.replace_succ(early_call_blk, callee_root_blk)
            callee_root_blk.preds = early_call_blk.preds

        if callee_leaf_blk.stms and callee_leaf_blk.stms[-1].is_a(RET):
            callee_leaf_blk.stms.pop()
        callee_leaf_blk.append_stm(JUMP(late_call_blk))
        callee_leaf_blk.succs = [late_call_blk]
        late_call_blk.preds = [callee_leaf_blk]

        if caller_scope.leaf_block is early_call_blk:
            caller_scope.leaf_block = late_call_blk


class CallCollector(IRVisitor):
    def __init__(self, funcalls, methodcalls):
        super().__init__()
        self.funcalls = funcalls
        self.methodcalls = methodcalls

    def visit_CALL(self, ir):
        if ir.func_scope.is_method():
            self.methodcalls[(self.scope, ir.func_scope)].add((ir, self.current_stm))
        else:
            self.funcalls[(self.scope, ir.func_scope)].add((ir, self.current_stm))

    def visit_NEW(self, ir):
        assert ir.func_scope.is_class()
        ctor = ir.func_scope.find_ctor()
        assert ctor
        self.methodcalls[(self.scope, ctor)].add((ir, self.current_stm))

class SymbolReplacer(IRVisitor):
    def __init__(self, sym_map, inst_name = None):
        super().__init__()
        self.sym_map = sym_map
        self.inst_name = inst_name

    def traverse_blocks(self, root_block, full=False, longitude=False):
        assert len(root_block.preds) == 0
        visited = set()
        yield from root_block.traverse(visited, full=False, longitude=False)

    def process(self, scope, root_block):
        self.scope = scope
        for blk in self.traverse_blocks(root_block):
            self._process_block(blk)

    def visit_TEMP(self, ir):
        if ir.sym in self.sym_map:
            rep = self.sym_map[ir.sym]
            if isinstance(rep, Symbol):
                ir.sym = rep
            else:
                self.current_stm.replace(ir, rep)

    def visit_ATTR(self, ir):
        if self.inst_name and ir.head().name == env.self_name:
            ir.attr = Symbol.new('{}_{}'.format(self.inst_name, ir.attr.name), self.scope)
        #self.visit(ir.exp)
        #if ir.attr in self.sym_map:
        #    ir.attr = self.sym_map[ir.attr]

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
        if self.scope.is_method():
            return
        flatname = self.make_flatname(ir)
        flatsym = self.scope.gen_sym(flatname)
        newtemp = TEMP(flatsym, ir.ctx)
        self.current_stm.replace(ir, newtemp)

    def visit_CALL(self, ir):
        # we don't flatten a method call
        return

            