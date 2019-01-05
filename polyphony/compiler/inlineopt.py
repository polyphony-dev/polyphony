from collections import defaultdict, deque
from .block import Block
from .irvisitor import IRVisitor, IRTransformer
from .ir import Ctx, IR, CONST, TEMP, ATTR, CALL, MOVE, EXPR, RET, JUMP
from .env import env
from .copyopt import CopyOpt
from .symbol import Symbol
from .synth import merge_synth_params
from .type import Type
from .usedef import UseDefDetector
from .varreplacer import VarReplacer
import logging
logger = logging.getLogger()


class InlineOpt(object):
    def __init__(self):
        pass

    def process_all(self, driver):
        self.dones = set()
        self.inline_counts = defaultdict(int)
        scopes = driver.get_scopes()
        for scope in scopes:
            if scope not in self.dones:
                self._process_scope(scope)

    def _process_scope(self, scope):
        calls = defaultdict(list)
        collector = CallCollector(calls)
        collector.process(scope)
        for callee, calls in calls.items():
            self._process_scope(callee)
            if callee.is_lib() or callee.is_pure():
                continue
            elif callee.is_method():
                self._process_method(callee, scope, calls)
            else:
                self._process_func(callee, scope, calls)
        self.dones.add(scope)
        if calls:
            self._reduce_useless_move(scope)

    def _process_func(self, callee, caller, calls):
        if callee.is_testbench():
            return
        if caller.is_testbench() and callee.is_function_module():
            return
        for call, call_stm in calls:
            self.inline_counts[caller] += 1
            assert callee is call.func_scope()

            symbol_map = self._make_replace_symbol_map(call,
                                                       caller,
                                                       callee,
                                                       str(self.inline_counts[caller]))
            if callee.is_returnable():
                self._make_result_exp(call_stm, call, callee, caller, symbol_map)

            block_map, _ = callee.clone_blocks(caller)
            callee_entry_blk = block_map[callee.entry_block]
            callee_exit_blk = block_map[callee.exit_block]
            assert len(callee_exit_blk.succs) <= 1
            sym_replacer = SymbolReplacer(symbol_map)
            sym_replacer.process(caller, callee_entry_blk)

            self._merge_blocks(call_stm, callee_entry_blk, callee_exit_blk)

            if call_stm.is_a(EXPR):
                call_stm.block.stms.remove(call_stm)

    def _process_method(self, callee, caller, calls):
        if caller.is_namespace():
            return
        if callee.is_ctor() and callee.parent.is_module():
            if caller.is_ctor() and caller.parent.is_module():
                pass
            else:
                return
        for call, call_stm in calls:
            self.inline_counts[caller] += 1

            symbol_map = self._make_replace_symbol_map(call,
                                                       caller,
                                                       callee,
                                                       str(self.inline_counts[caller]))
            if callee.is_returnable():
                self._make_result_exp(call_stm, call, callee, caller, symbol_map)

            attr_map = {}
            if caller.is_method() and caller.parent is not callee.parent:
                if callee.is_ctor():
                    assert not callee.is_returnable()
                    if call_stm.is_a(MOVE):
                        callee_self = call_stm.dst.clone()
                        callee_self.ctx = Ctx.LOAD
                        attr_map[callee.symbols[env.self_name]] = callee_self
                else:
                    if call_stm.is_a(MOVE):
                        object_sym = call.func.exp.qualified_symbol()
                    elif call_stm.is_a(EXPR):
                        object_sym = call.func.exp.qualified_symbol()
                    symbol_map[callee.symbols[env.self_name]] = object_sym
                    object_sym[0].add_tag('inlined')
            else:
                if callee.is_ctor():
                    assert not callee.is_returnable()
                    if call_stm.is_a(MOVE):
                        assert call_stm.src is call
                        object_sym = call_stm.dst.qualified_symbol()
                    else:
                        assert False
                else:
                    object_sym = call.func.exp.qualified_symbol()
                symbol_map[callee.symbols[env.self_name]] = object_sym
                object_sym[0].add_tag('inlined')
            block_map, _ = callee.clone_blocks(caller)
            callee_entry_blk = block_map[callee.entry_block]
            callee_exit_blk = block_map[callee.exit_block]
            assert len(callee_exit_blk.succs) <= 1
            sym_replacer = SymbolReplacer(symbol_map, attr_map)
            sym_replacer.process(caller, callee_entry_blk)

            self._merge_blocks(call_stm, callee_entry_blk, callee_exit_blk)

            if callee.is_ctor():
                assert call_stm.src is call
                call_stm.block.stms.remove(call_stm)
            elif call_stm.is_a(EXPR):
                call_stm.block.stms.remove(call_stm)

    def _make_result_exp(self, call_stm, call, callee, caller, symbol_map):
        result_sym = symbol_map[callee.symbols[Symbol.return_prefix]]
        result_sym.name = callee.orig_name + '_result' + str(self.inline_counts[caller])
        assert result_sym.is_return()
        result_sym.del_tag('return')
        result = TEMP(result_sym, Ctx.LOAD)
        result.lineno = call_stm.lineno
        if call_stm.is_a(MOVE):
            assert call_stm.src is call
            call_stm.src = result
        elif call_stm.is_a(EXPR):
            assert call_stm.exp is call
            call_stm.exp = result

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
            if arg.is_a([TEMP, ATTR, CONST]):
                symbol_map[p] = arg.clone()
            else:
                assert False
        return symbol_map

    def _merge_blocks(self, call_stm, callee_entry_blk, callee_exit_blk):
        caller_scope = call_stm.block.scope
        early_call_blk = call_stm.block
        late_call_blk  = Block(caller_scope)
        late_call_blk.succs = early_call_blk.succs
        late_call_blk.succs_loop = early_call_blk.succs_loop
        late_call_blk.synth_params = early_call_blk.synth_params.copy()
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

        self._merge_synth_params(early_call_blk.synth_params, late_call_blk, callee_entry_blk, callee_exit_blk)

    def _merge_synth_params(self, synth_params, late_call_blk, callee_entry_blk, callee_exit_blk):
        assert synth_params
        visited = set([late_call_blk])
        for blk in callee_entry_blk.traverse(visited):
            merge_synth_params(blk.synth_params, synth_params)

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
        self.calls[ir.func_scope()].append((ir, self.current_stm))

    def visit_NEW(self, ir):
        assert ir.func_scope().is_class()
        ctor = ir.func_scope().find_ctor()
        assert ctor
        self.calls[ctor].append((ir, self.current_stm))


class SymbolReplacer(IRVisitor):
    def __init__(self, sym_map, attr_map=None, inst_name=None):
        super().__init__()
        self.sym_map = sym_map
        self.attr_map = attr_map
        self.inst_name = inst_name

    def traverse_blocks(self, entry_block):
        assert len(entry_block.preds) == 0
        visited = set()
        yield from entry_block.traverse(visited)

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

    def visit_ARRAY(self, ir):
        self.visit(ir.repeat)
        for item in ir.items:
            self.visit(item)
        if ir.sym in self.sym_map:
            rep = self.sym_map[ir.sym]
            ir.sym = rep


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


class FlattenFieldAccess(IRTransformer):
    def _make_flatname(self, qsym):
        qnames = [sym.name for sym in qsym if sym.name != env.self_name]
        return '_'.join(qnames)

    def _make_flatten_qsym(self, ir):
        assert ir.is_a(ATTR)
        flatname = None
        inlining_scope = ir.head().scope
        qsym = ir.qualified_symbol()
        if qsym[-1].typ.is_function():
            tail = (qsym[-1], )
            qsym = qsym[:-1]
        else:
            tail = tuple()

        ancestor = qsym[-1]
        for i, sym in enumerate(qsym):
            if (sym.typ.is_object() and not sym.is_subobject() and
                    sym.typ.get_scope().is_module()):
                flatname = self._make_flatname(qsym[i + 1:])
                head = qsym[:i + 1]
                scope = sym.typ.get_scope()
                break
        else:
            flatname = self._make_flatname(qsym)
            head = tuple()
            scope = inlining_scope
        if flatname:
            if scope.has_sym(flatname):
                flatsym = scope.find_sym(flatname)
            else:
                tags = set()
                for sym in ir.qualified_symbol():
                    tags |= sym.tags
                flatsym = scope.add_sym(flatname, tags, typ=ancestor.typ.clone())
                flatsym.ancestor = ancestor
                flatsym.add_tag('flattened')
            return head + (flatsym, ) + tail
        else:
            return head + tail

    def _make_new_ATTR(self, qsym, ir):
        newir = TEMP(qsym[0], Ctx.LOAD)
        newir.lineno = ir.lineno
        for sym in qsym[1:]:
            newir = ATTR(newir, sym, Ctx.LOAD)
            newir.lineno = ir.lineno
        newir.ctx = ir.ctx
        return newir

    def visit_ATTR(self, ir):
        # don't flatten use of the other instance in the class except module
        if self.scope.is_method():
            if self.scope.parent.is_module():
                pass
            else:
                return ir
        # don't flatten use of the static class field
        if ir.tail().typ.is_class():
            return ir
        qsym = self._make_flatten_qsym(ir)
        newattr = self._make_new_ATTR(qsym, ir)
        newattr.lineno = ir.lineno
        newattr.attr_scope = ir.attr_scope
        return newattr


class FlattenObjectArgs(IRTransformer):
    def __init__(self):
        self.params_modified_scopes = set()

    def visit_EXPR(self, ir):
        if (ir.exp.is_a(CALL) and ir.exp.func_scope().is_method() and
                ir.exp.func_scope().parent.is_module()):
            if ir.exp.func_scope().orig_name == 'append_worker':
                self._flatten_args(ir.exp)
        self.new_stms.append(ir)

    def _flatten_args(self, call):
        args = []
        for pindex, (name, arg) in enumerate(call.args):
            if arg.is_a([TEMP, ATTR]) and arg.symbol().typ.is_object() and not arg.symbol().typ.get_scope().is_port():
                flatten_args = self._flatten_object_args(call, arg, pindex)
                args.extend(flatten_args)
            else:
                args.append((name, arg))
        call.args = args

    def _flatten_object_args(self, call, arg, pindex):
        worker_scope = call.args[0][1].symbol().typ.get_scope()
        args = []
        base_name = arg.symbol().name
        module_scope = self.scope.parent
        object_scope = arg.symbol().typ.get_scope()
        assert object_scope.is_class()
        flatten_args = []
        for fname, fsym in object_scope.class_fields().items():
            if fsym.typ.is_function():
                continue
            if ((fsym.typ.is_object() and fsym.typ.get_scope().is_port()) or
                    fsym.typ.is_scalar()):
                new_name = '{}_{}'.format(base_name, fname)
                new_sym = module_scope.find_sym(new_name)
                if not new_sym:
                    new_sym = module_scope.add_sym(new_name, typ=fsym.typ.clone())
                new_arg = arg.clone()
                new_arg.set_symbol(new_sym)
                args.append((new_name, new_arg))
                flatten_args.append((fname, fsym))
        if worker_scope not in self.params_modified_scopes:
            self._flatten_scope_params(worker_scope, pindex, flatten_args)
            self.params_modified_scopes.add(worker_scope)
        return args

    def _flatten_scope_params(self, worker_scope, pindex, flatten_args):
        flatten_params = []
        in_sym, sym, _ = worker_scope.params[pindex]
        base_name = sym.name
        for name, sym in flatten_args:
            new_name = '{}_{}'.format(base_name, name)
            param_in = worker_scope.find_param_sym(new_name)
            if not param_in:
                param_in = worker_scope.add_param_sym(new_name, typ=sym.typ.clone())
            param_copy = worker_scope.find_sym(new_name)
            if not param_copy:
                param_copy = worker_scope.add_sym(new_name, typ=sym.typ.clone())
            flatten_params.append((param_in, param_copy))
        new_params = []
        for idx, (sym, copy, defval) in enumerate(worker_scope.params):
            if idx == pindex:
                for new_sym, new_copy in flatten_params:
                    new_params.append((new_sym, new_copy, None))
            else:
                new_params.append((sym, copy, defval))
        worker_scope.params.clear()
        for sym, copy, defval in new_params:
            worker_scope.add_param(sym, copy, defval)
        for stm in worker_scope.entry_block.stms[:]:
            if stm.is_a(MOVE) and stm.src.is_a(TEMP) and stm.src.symbol() is in_sym:
                insert_idx = worker_scope.entry_block.stms.index(stm)
                worker_scope.entry_block.stms.remove(stm)
                for new_sym, new_copy in flatten_params:
                    mv = MOVE(TEMP(new_copy, Ctx.STORE), TEMP(new_sym, Ctx.LOAD))
                    mv.lineno = mv.dst.lineno = mv.src.lineno = stm.lineno
                    worker_scope.entry_block.insert_stm(insert_idx, mv)
                break


class FlattenModule(IRTransformer):
    '''
    self.sub.append_worker(self.sub.worker, ...)  =>  self.append_worker(self.worker, ...)
    '''
    def __init__(self, driver):
        self.driver = driver

    def process(self, scope):
        if scope.parent and scope.parent.is_module() and scope is scope.parent.find_ctor():
            super().process(scope)

    def visit_EXPR(self, ir):
        if (ir.exp.is_a(CALL) and ir.exp.func_scope().is_method() and
                ir.exp.func_scope().parent.is_module() and
                ir.exp.func_scope().orig_name == 'append_worker' and
                ir.exp.func.head().name == env.self_name and
                len(ir.exp.func.qualified_symbol()) > 2):
            call = ir.exp
            _, arg = call.args[0]
            new_arg = self._make_new_worker(arg)
            assert self.scope.parent.is_module()
            append_worker_sym = self.scope.parent.find_sym('append_worker')
            assert append_worker_sym
            self_var = TEMP(call.func.head(), Ctx.LOAD)
            new_func = ATTR(self_var, append_worker_sym, Ctx.LOAD)
            new_func.attr_scope = append_worker_sym.scope
            self_var.lineno = new_func.lineno = call.func.lineno
            call.func = new_func
            call.args[0] = (None, new_arg)
        self.new_stms.append(ir)

    def _make_new_worker(self, arg):
        parent_module = self.scope.parent
        worker_scope = arg.attr.typ.get_scope()
        inst_name = arg.tail().name
        new_worker = worker_scope.clone(inst_name, str(arg.lineno), parent=parent_module)
        UseDefDetector().process(new_worker)
        worker_self = new_worker.find_sym('self')
        worker_self.typ.set_scope(parent_module)
        new_exp = arg.exp.clone()
        ctor_self = self.scope.find_sym('self')
        new_exp.replace(ctor_self, worker_self)
        VarReplacer.replace_uses(TEMP(worker_self, Ctx.LOAD), new_exp, new_worker.usedef)
        new_worker_sym = parent_module.add_sym(new_worker.orig_name,
                                               typ=Type.function(new_worker, None, None))
        arg.exp = arg.exp.exp
        arg.attr = new_worker_sym
        self.driver.insert_scope(new_worker)
        return arg


class ObjectHierarchyCopier(object):
    def __init__(self):
        pass

    def _is_inlining_object(self, ir):
        return (ir.is_a([TEMP, ATTR]) and
                not ir.symbol().is_param() and
                ir.symbol().typ.is_object() and
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
                new_cp.lineno = new_src.lineno = new_dst.lineno = cp.lineno
                cp_idx = cp.block.stms.index(cp)
                cp.block.insert_stm(cp_idx + 1, new_cp)
                if sym.typ.is_object():
                    worklist.append(new_cp)
