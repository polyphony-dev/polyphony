from collections import defaultdict, deque
from .block import Block
from .irvisitor import IRVisitor
from .ir import Ctx, IR, CONST, TEMP, ATTR, MOVE, EXPR, RET, JUMP
from .env import env
from .copyopt import CopyOpt
from .symbol import Symbol
import logging
logger = logging.getLogger()


class InlineOpt(object):
    def __init__(self):
        pass

    def process_all(self):
        self.dones = set()
        self.inline_counts = defaultdict(int)
        for scope in env.call_graph.bfs_ordered_nodes():
            if scope not in self.dones:
                self._process_scope(scope)

    def _process_scope(self, scope):
        calls = defaultdict(list)
        collector = CallCollector(calls)
        collector.process(scope)
        for callee, calls in calls.items():
            self._process_scope(callee)
            if callee.is_lib():
                continue
            elif callee.is_method():
                self._process_method(callee, scope, calls)
            else:
                self._process_func(callee, scope, calls)
        self.dones.add(scope)
        if calls:
            self._reduce_useless_move(scope)

    def _process_func(self, callee, caller, calls):
        if callee.is_function_module() or callee.is_testbench():
            return
        for call, call_stm in calls:
            self.inline_counts[caller] += 1
            assert callee is call.func_scope

            symbol_map = self._make_replace_symbol_map(call,
                                                       caller,
                                                       callee,
                                                       str(self.inline_counts[caller]))
            result_sym = symbol_map[callee.symbols[Symbol.return_prefix]]
            result_sym.name = callee.orig_name + '_result' + str(self.inline_counts[caller])
            assert result_sym.is_return()
            result_sym.del_tag('return')

            block_map, _ = callee.clone_blocks(caller)
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

            if call_stm.is_a(EXPR):
                call_stm.block.stms.remove(call_stm)

    def _process_method(self, callee, caller, calls):
        if caller.is_global():
            return
        for call, call_stm in calls:
            self.inline_counts[caller] += 1

            symbol_map = self._make_replace_symbol_map(call,
                                                       caller,
                                                       callee,
                                                       str(self.inline_counts[caller]))
            result_sym = symbol_map[callee.symbols[Symbol.return_prefix]]
            result_sym.name = callee.orig_name + '_result' + str(self.inline_counts[caller])
            assert result_sym.is_return()
            result_sym.del_tag('return')

            block_map, _ = callee.clone_blocks(caller)
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
            elif call_stm.is_a(EXPR):
                call_stm.block.stms.remove(call_stm)

    def _make_replace_symbol_map(self, call, caller, callee, inline_id):
        symbol_map = callee.clone_symbols(caller, postfix='_inl' + inline_id)
        if callee.is_method():
            params = callee.params[1:]
        else:
            params = callee.params[:]
        for i, (p, copy, defval) in enumerate(params):
            if len(call.args) > i:
                _, arg = call.args[i]
            else:
                arg = defval
            if arg.is_a(TEMP):
                symbol_map[p] = arg.sym
                symbol_map[copy] = arg.sym
            elif arg.is_a(CONST):
                symbol_map[p] = arg
            elif arg.is_a(ATTR):
                symbol_map[p] = arg
            else:
                assert False
        return symbol_map

    def _merge_blocks(self, call_stm, callee_entry_blk, callee_exit_blk):
        caller_scope = call_stm.block.scope
        early_call_blk = call_stm.block
        late_call_blk  = Block(caller_scope)
        late_call_blk.succs = early_call_blk.succs
        late_call_blk.succs_loop = early_call_blk.succs_loop
        for succ in late_call_blk.succs:
            succ.replace_pred(early_call_blk, late_call_blk)
            succ.replace_pred_loop(early_call_blk, late_call_blk)

        idx = early_call_blk.stms.index(call_stm)
        late_call_blk.stms = early_call_blk.stms[idx:]
        for s in late_call_blk.stms:
            s.block = late_call_blk
        early_call_blk.stms = early_call_blk.stms[:idx]
        early_call_blk.append_stm(JUMP(callee_entry_blk))
        early_call_blk.succs = [callee_entry_blk]
        early_call_blk.succs_loop = []
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
                if (stm.is_a(MOVE) and stm.dst.is_a(TEMP) and
                        stm.src.is_a(TEMP) and stm.dst.sym is stm.src.sym):
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
    def __init__(self, sym_map, attr_map=None, inst_name=None):
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
            elif isinstance(rep, tuple):  # qualified_symbol
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
                    if ir.attr.typ.is_object():
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
        if not mov.src.symbol().typ.is_object():
            return False
        if mov.src.symbol().typ.get_scope().is_port():
            return False
        if not mov.dst.is_a([TEMP, ATTR]):
            return False
        if not mov.dst.symbol().typ.is_object():
            return False
        if (mov.dst.is_a(ATTR) and mov.dst.tail().typ.is_object() and
                mov.dst.tail().typ.get_scope().is_module()):
            return False
        return True

    def visit_MOVE(self, ir):
        if not self._is_alias_def(ir):
            return
        if ir.src.symbol().is_param():
            return
        self.copies.append(ir)


class FlattenFieldAccess(IRVisitor):
    def _make_flatname(self, qsym):
        qnames = [sym.name for sym in qsym if sym.name != env.self_name]
        return '_'.join(qnames)

    def _make_flatten_qsym(self, ir):
        assert ir.is_a(ATTR)
        flatname = None
        receivers_scope = ir.tail().scope
        qsym = ir.qualified_symbol()
        if qsym[-1].typ.is_function():
            tail = (qsym[-1], )
            qsym = qsym[:-1]
        else:
            tail = tuple()

        ancestor = qsym[-1]
        for i, sym in enumerate(qsym):
            if sym.typ.is_object() and sym.typ.get_scope().is_module():
                flatname = self._make_flatname(qsym[i + 1:])
                head = qsym[:i + 1]
                scope = sym.typ.get_scope()
                break
        else:
            flatname = self._make_flatname(qsym)
            head = tuple()
            scope = receivers_scope
        if flatname:
            if scope.has_sym(flatname):
                flatsym = scope.find_sym(flatname)
            else:
                flatsym = scope.add_sym(flatname, ir.attr.tags)
                flatsym.typ = ancestor.typ
                if flatsym.typ.is_object() and flatsym.typ.get_scope().is_port():
                    # we use a flattened name for the port
                    flatsym.ancestor = None
                else:
                    flatsym.ancestor = ancestor
            return head + (flatsym, ) + tail
        else:
            return head + tail

    def _make_new_ATTR(self, qsym, ir):
        newir = TEMP(qsym[0], Ctx.LOAD)
        for sym in qsym[1:]:
            newir = ATTR(newir, sym, Ctx.LOAD)
        newir.ctx = ir.ctx
        return newir

    def visit_ATTR(self, ir):
        # don't flatten use of the other instance in the class except module
        if self.scope.is_method():
            if self.scope.parent.is_module():
                pass
            else:
                return
        # don't flatten use of the static class field
        if ir.tail().typ.is_class():
            return
        qsym = self._make_flatten_qsym(ir)
        newattr = self._make_new_ATTR(qsym, ir)
        newattr.lineno = ir.lineno
        newattr.attr_scope = ir.attr_scope
        self.current_stm.replace(ir, newattr)


class ObjectHierarchyCopier(object):
    def __init__(self):
        pass

    def _is_inlining_object(self, ir):
        return (ir.is_a([TEMP, ATTR]) and ir.symbol().typ.is_object() and
                not ir.symbol().typ.get_scope().is_module())

    def _is_object_copy(self, mov):
        return self._is_inlining_object(mov.src) and self._is_inlining_object(mov.dst)

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
            class_scope = cp.src.symbol().typ.get_scope()
            assert class_scope is cp.dst.symbol().typ.get_scope()
            for sym in class_scope.class_fields().values():
                if not sym.typ.is_object():
                    continue
                new_dst = ATTR(cp.dst.clone(), sym, Ctx.STORE)
                new_src = ATTR(cp.src.clone(), sym, Ctx.LOAD)
                new_cp = MOVE(new_dst, new_src)
                new_dst.lineno = cp.lineno
                new_src.lineno = cp.lineno
                new_cp.lineno = cp.lineno
                cp_idx = cp.block.stms.index(cp)
                cp.block.insert_stm(cp_idx + 1, new_cp)
                if sym.typ.is_object():
                    worklist.append(new_cp)
