from collections import defaultdict, deque
from ..block import Block
from ..builtin import builtin_symbols
from ..irvisitor import IRVisitor, IRTransformer
from ..ir import Ctx, IR, CONST, UNOP, TEMP, ATTR, CALL, SYSCALL, MOVE, EXPR, RET, JUMP
from ..symbol import Symbol
from ..synth import merge_synth_params
from ..types.type import Type
from ..analysis.usedef import UseDefDetector
from ...common.env import env
from ...common.common import fail
from ...common.errors import Errors
import logging
logger = logging.getLogger()


class InlineOpt(object):
    inline_counts = 0

    def __init__(self):
        self.new_scopes = []

    def process_all(self, driver):
        self.processed_scopes = set()
        scopes = driver.scopes
        self.process_scopes(driver.scopes)
        self.process_scopes(self.new_scopes)

    def process_scopes(self, scopes):
        call_graph = {}
        for scope in scopes:
            self._build_call_graph_rec(scope, call_graph)

        callers = set()
        while call_graph:
            leaf = self._pop_leaf(call_graph)
            if not leaf:
                continue
            caller, callee, call_irs = leaf
            if callee.is_method():
                self._process_method(callee, caller, call_irs)
            else:
                self._process_func(callee, caller, call_irs)
            logger.debug(f"inlined {callee.name} on {caller.name}")
            # logger.debug(scope)
            callers.add(caller)
        for c in callers:
            self._reduce_useless_move(c)

    def _build_call_graph_rec(self, scope, call_graph):
        if scope in call_graph:
            return
        calls = defaultdict(list)
        collector = CallCollector(calls)
        collector.process(scope)
        if calls:
            call_graph[scope] = calls
            for callee in calls.keys():
                self._build_call_graph_rec(callee, call_graph)

    def _pop_leaf(self, call_graph):
        for scope, calls in call_graph.copy().items():
            for callee in calls.copy().keys():
                if callee not in call_graph:
                    call_irs = calls.pop(callee)
                    if not calls:
                        call_graph.pop(scope)
                    if callee.is_lib() or callee.is_pure():
                        continue
                    return scope, callee, call_irs
        return None

    def _process_func(self, callee, caller, call_irs):
        if callee.is_testbench():
            return
        if not env.config.perfect_inlining:
            if caller.is_testbench() and callee.is_function_module():
                return
        for call, call_stm in call_irs:
            self.inline_counts += 1
            assert callee is call.callee_scope

            symbol_map = self._make_replace_symbol_map(call,
                                                       caller,
                                                       callee,
                                                       str(self.inline_counts))
            if callee.is_returnable():
                self._make_result_exp(call_stm, call, callee, caller, symbol_map)

            block_map, _ = callee.clone_blocks(caller)
            callee_entry_blk = block_map[callee.entry_block]
            callee_exit_blk = block_map[callee.exit_block]
            assert len(callee_exit_blk.succs) <= 1
            sym_replacer = SymbolReplacer(symbol_map)
            sym_replacer.process(caller, callee_entry_blk)

            self._merge_blocks(call_stm, False, callee_entry_blk, callee_exit_blk)

            if call_stm.is_a(EXPR):
                call_stm.block.stms.remove(call_stm)

            if callee.is_enclosure():
                self._process_enclosure(callee, caller,
                                        symbol_map, {},
                                        str(self.inline_counts))

    def _process_method(self, callee, caller, call_irs):
        if caller.is_namespace():
            return
        if callee.is_ctor() and callee.parent.is_module():
            if caller.is_ctor() and caller.parent.is_module():
                pass
            else:
                # TODO
                pass
        for call, call_stm in call_irs:
            self.inline_counts += 1

            symbol_map = self._make_replace_symbol_map(call,
                                                       caller,
                                                       callee,
                                                       str(self.inline_counts))
            if callee.is_returnable():
                self._make_result_exp(call_stm, call, callee, caller, symbol_map)

            attr_map = {}
            if caller.is_method() and caller.parent is not callee.parent:
                if callee.is_ctor():
                    assert not callee.is_returnable()
                    if call_stm.is_a(MOVE):
                        callee_self = call_stm.dst.clone(ctx=Ctx.LOAD)
                        attr_map[callee.symbols[env.self_name]] = callee_self
                        object_sym = call_stm.dst.qualified_symbol
                        object_sym[0].add_tag('inlined')
                    else:
                        continue
                else:
                    if call_stm.is_a(MOVE):
                        object_sym = call.func.exp.qualified_symbol
                    elif call_stm.is_a(EXPR):
                        object_sym = call.func.exp.qualified_symbol
                    symbol_map[callee.symbols[env.self_name]] = object_sym
                    object_sym[0].add_tag('inlined')
            else:
                if callee.is_ctor():
                    assert not callee.is_returnable()
                    if call_stm.is_a(MOVE):
                        assert call_stm.src is call
                        object_sym = call_stm.dst.qualified_symbol
                    else:
                        continue
                else:
                    object_sym = call.func.exp.qualified_symbol
                symbol_map[callee.symbols[env.self_name]] = object_sym
                object_sym[0].add_tag('inlined')
            block_map, _ = callee.clone_blocks(caller)
            callee_entry_blk = block_map[callee.entry_block]
            callee_exit_blk = block_map[callee.exit_block]
            assert len(callee_exit_blk.succs) <= 1
            sym_replacer = SymbolReplacer(symbol_map, attr_map)
            sym_replacer.process(caller, callee_entry_blk)

            self._merge_blocks(call_stm, callee.is_ctor(), callee_entry_blk, callee_exit_blk)

            if callee.is_ctor():
                assert call_stm.src is call
                cls_scope = callee.parent
                cls_sym = cls_scope.parent.find_sym(cls_scope.base_name)
                builtin_new = SYSCALL(builtin_symbols['$new'],
                                      args=[('typ', TEMP(cls_sym, Ctx.LOAD))],
                                      kwargs={})
                call_stm.replace(call_stm.src, builtin_new)
            elif call_stm.is_a(EXPR):
                call_stm.block.stms.remove(call_stm)

            if callee.is_enclosure():
                self._process_enclosure(callee, caller,
                                        symbol_map, attr_map,
                                        str(self.inline_counts))

    def _make_result_exp(self, call_stm, call, callee, caller, symbol_map):
        result_sym = symbol_map[callee.symbols[Symbol.return_prefix]]
        result_sym.name = f'{callee.base_name}_result{self.inline_counts}'
        assert result_sym.is_return()
        result_sym.del_tag('return')
        result = TEMP(result_sym, Ctx.LOAD)
        if call_stm.is_a(MOVE):
            assert call_stm.src is call
            call_stm.src = result
        elif call_stm.is_a(EXPR):
            assert call_stm.exp is call
            call_stm.exp = result

    def _make_replace_symbol_map(self, call, caller, callee, inline_id):
        symbol_map = callee.clone_symbols(caller, postfix='_inl' + inline_id)
        param_symbols = callee.param_symbols()
        param_values = callee.param_default_values()
        for i, (sym, defval) in enumerate(zip(param_symbols, param_values)):
            if len(call.args) > i:
                _, arg = call.args[i]
            else:
                arg = defval
            if arg.is_a([TEMP, ATTR, CONST, UNOP]):
                symbol_map[sym] = arg.clone()
            else:
                assert False
        return symbol_map

    def _merge_blocks(self, call_stm, is_ctor, callee_entry_blk, callee_exit_blk):
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
        if is_ctor:
            idx += 1
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
        for blk in callee_entry_blk.traverse():
            if blk is late_call_blk:
                continue
            merge_synth_params(blk.synth_params, synth_params)

    def _reduce_useless_move(self, scope):
        for block in scope.traverse_blocks():
            removes = []
            for stm in block.stms:
                if (stm.is_a(MOVE) and stm.dst.is_a(TEMP) and
                        stm.src.is_a(TEMP) and stm.dst.symbol is stm.src.symbol):
                    removes.append(stm)
            for rm in removes:
                block.stms.remove(rm)

    def _process_enclosure(self, enclosure, caller, symbol_map, attr_map, inline_id):
        caller.add_tag('enclosure')
        for clos in enclosure.closures:
            clos_sym = enclosure.symbols[clos.base_name]
            new_clos_sym = symbol_map[clos_sym]

            new_clos = clos.clone('', postfix=f'inl{inline_id}', parent=caller, sym_postfix=f'_{inline_id}')
            new_clos_sym.typ = new_clos_sym.typ.clone(scope=new_clos)

            sym_replacer = SymbolReplacer(symbol_map, attr_map)
            sym_replacer.process(new_clos, new_clos.entry_block)
            for sym in new_clos.free_symbols.copy():
                if sym in symbol_map:
                    sym_or_ir = symbol_map[sym]
                    if isinstance(sym_or_ir, IR):
                        if sym_or_ir.is_a(TEMP):
                            new_sym = sym_or_ir.symbol
                        elif sym_or_ir.is_a(ATTR):
                            new_sym = sym_or_ir.head()
                        else:
                            assert False
                    elif isinstance(sym_or_ir, tuple):
                        new_sym = sym_or_ir[0]
                    else:
                        assert isinstance(sym_or_ir, Symbol)
                        new_sym = sym_or_ir
                    new_clos.add_free_sym(new_sym)
                    new_clos.del_free_sym(sym)
            caller.add_closure(new_clos)
            self.new_scopes.append(new_clos)


class CallCollector(IRVisitor):
    def __init__(self, calls):
        super().__init__()
        self.calls = calls

    def visit_CALL(self, ir):
        callee_scope = ir.callee_scope
        self.calls[callee_scope].append((ir, self.current_stm))

    def visit_NEW(self, ir):
        callee_scope = ir.callee_scope
        assert callee_scope.is_class()
        ctor = callee_scope.find_ctor()
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
        yield from entry_block.traverse()

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
        ret_ir = ir
        if self.attr_map and ir.symbol in self.attr_map:
            attr = self.attr_map[ir.symbol].clone()
            ret_ir = attr
        elif ir.symbol in self.sym_map:
            rep = self.sym_map[ir.symbol]
            if isinstance(rep, Symbol):
                ir.symbol = rep
                ret_ir = ir
            elif isinstance(rep, tuple):  # qualified_symbol
                ret_ir = self._qsym_to_var(rep, ir.ctx)
            else:
                self.current_stm.replace(ir, rep)
                ret_ir = rep
        if ret_ir.is_a([TEMP, ATTR]):
            for expr in Type.find_expr(ret_ir.symbol.typ):
                assert expr.is_a(EXPR)
                old_stm = self.current_stm
                self.current_stm = expr
                self.visit(expr)
                self.current_stm = old_stm
        return ret_ir

    def visit_ATTR(self, ir):
        exp = self.visit(ir.exp)
        if exp:
            ir.exp = exp

        if ir.symbol in self.sym_map:
            ir.symbol = self.sym_map[ir.symbol]

        for expr in Type.find_expr(ir.symbol.typ):
            assert expr.is_a(EXPR)
            old_stm = self.current_stm
            self.current_stm = expr
            self.visit(expr)
            self.current_stm = old_stm

    def visit_ARRAY(self, ir):
        self.visit(ir.repeat)
        for item in ir.items:
            self.visit(item)
        if ir.symbol in self.sym_map:
            rep = self.sym_map[ir.symbol]
            ir.symbol = rep


class FlattenFieldAccess(IRTransformer):
    def _make_flatname(self, qsym):
        qnames = [sym.name for sym in qsym if sym.name != env.self_name]
        return '_'.join(qnames)

    def _make_flatten_qsym(self, ir):
        assert ir.is_a(ATTR)
        flatname = None
        inlining_scope = ir.head().scope
        qsym = ir.qualified_symbol
        if qsym[-1].typ.is_function():
            tail = (qsym[-1], )
            qsym = qsym[:-1]
        else:
            tail = tuple()

        ancestor = qsym[-1]
        for i, sym in enumerate(qsym):
            if (sym.typ.is_object() and not sym.is_subobject() and
                    sym.typ.scope.is_module()):
                flatname = self._make_flatname(qsym[i + 1:])
                head = qsym[:i + 1]
                scope = sym.typ.scope
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
                for sym in ir.qualified_symbol:
                    tags |= sym.tags
                flatsym = scope.add_sym(flatname, tags, typ=ancestor.typ)
                flatsym.ancestor = ancestor
                flatsym.add_tag('flattened')
            return head + (flatsym, ) + tail
        else:
            return head + tail

    def _make_new_ATTR(self, qsym, ir):
        def context(i):
            return ir.ctx if i == len(qsym) - 1 else Ctx.LOAD
        newir = TEMP(qsym[0], context(0))
        for i in range(1, len(qsym)):
            newir = ATTR(newir, qsym[i], context(i))
        assert newir.ctx == ir.ctx
        return newir

    def visit_TEMP(self, ir):
        for expr in Type.find_expr(ir.symbol.typ):
            assert expr.is_a(EXPR)
            old_stm = self.current_stm
            self.current_stm = expr
            expr.exp = self.visit(expr.exp)
            self.current_stm = old_stm
        return ir

    def visit_ATTR(self, ir):
        for expr in Type.find_expr(ir.symbol.typ):
            assert expr.is_a(EXPR)
            old_stm = self.current_stm
            self.current_stm = expr
            expr.exp = self.visit(expr.exp)
            self.current_stm = old_stm

        # don't flatten use of the other instance in the class except module
        if self.scope.is_method():
            if self.scope.parent.is_module():
                pass
            else:
                return ir
        if not ir.tail().typ.is_object():
            return ir
        object_scope = ir.tail().typ.scope
        if object_scope.is_interface():
            return ir
        if object_scope.is_module():
            return ir
        if object_scope.is_port():
            return ir

        qsym = self._make_flatten_qsym(ir)
        newattr = self._make_new_ATTR(qsym, ir)
        return newattr


class FlattenObjectArgs(IRTransformer):
    def __init__(self):
        self.params_modified_scopes = set()

    def visit_EXPR(self, ir):
        if ir.exp.is_a(CALL):
            callee_scope = ir.exp.callee_scope
            if (callee_scope.is_method()
                    and callee_scope.parent.is_module()
                    and callee_scope.base_name == 'append_worker'):
                self._flatten_args(ir.exp)
        self.new_stms.append(ir)

    def _flatten_args(self, call):
        args = []
        for pindex, (name, arg) in enumerate(call.args):
            if (arg.is_a([TEMP, ATTR])
                    and arg.symbol.typ.is_object()
                    and not arg.symbol.typ.scope.is_port()):
                flatten_args = self._flatten_object_args(call, arg, pindex)
                args.extend(flatten_args)
            else:
                args.append((name, arg))
        call.args = args

    def _flatten_object_args(self, call, arg, pindex):
        worker_scope = call.args[0][1].symbol.typ.scope
        args = []
        base_name = arg.symbol.name
        module_scope = self.scope.parent
        object_scope = arg.symbol.typ.scope
        assert object_scope.is_class()
        flatten_args = []
        for fname, fsym in object_scope.class_fields().items():
            if fsym.typ.is_function():
                continue
            if ((fsym.typ.is_object() and fsym.typ.scope.is_port())
                    or fsym.typ.is_scalar()):
                new_name = '{}_{}'.format(base_name, fname)
                new_sym = module_scope.find_sym(new_name)
                if not new_sym:
                    new_sym = module_scope.add_sym(new_name, typ=fsym.typ)
                new_arg = arg.clone()
                new_arg.set_symbol(new_sym)
                args.append((new_name, new_arg))
                flatten_args.append((fname, fsym))
        if worker_scope not in self.params_modified_scopes:
            self._flatten_scope_params(worker_scope, pindex, flatten_args)
            self.params_modified_scopes.add(worker_scope)
        return args

    def _flatten_scope_params(self, worker_scope, pindex, flatten_args):
        assert False, 'need test'
        flatten_params = []
        sym = worker_scope.param_symbols()[pindex]
        base_name = sym.name
        for name, sym in flatten_args:
            new_name = '{}_{}'.format(base_name, name)
            param_in = worker_scope.find_param_sym(new_name)
            if not param_in:
                param_in = worker_scope.add_param_sym(new_name, typ=sym.typ)
            #param_copy = worker_scope.find_sym(new_name)
            #if not param_copy:
            #    param_copy = worker_scope.add_sym(new_name, typ=sym.typ)
            flatten_params.append(param_in)
        new_params = []
        for idx, (sym, defval) in enumerate(worker_scope.params):
            if idx == pindex:
                for new_sym in flatten_params:
                    new_params.append((new_sym, None))
            else:
                new_params.append((sym, defval))
        worker_scope.clear_params()
        for sym, defval in new_params:
            worker_scope.add_param(sym, defval)
        # for stm in worker_scope.entry_block.stms[:]:
        #     if stm.is_a(MOVE) and stm.src.is_a(TEMP) and stm.src.symbol is sym:
        #         insert_idx = worker_scope.entry_block.stms.index(stm)
        #         worker_scope.entry_block.stms.remove(stm)
        #         for new_sym, new_copy in flatten_params:
        #             mv = MOVE(TEMP(new_copy, Ctx.STORE), TEMP(new_sym, Ctx.LOAD))
        #             mv.loc = stm.loc
        #             worker_scope.entry_block.insert_stm(insert_idx, mv)
        #         break


class FlattenModule(IRVisitor):
    '''
    self.sub.append_worker(self.sub.worker, ...)  =>  self.append_worker(self.worker, ...)
    '''
    def __init__(self, driver):
        self.driver = driver

    def process(self, scope):
        if scope.parent and scope.parent.is_module(): # and scope is scope.parent.find_ctor():
            super().process(scope)

    def visit_CALL(self, ir):
        callee_scope = ir.callee_scope
        if (callee_scope.is_method() and
                callee_scope.parent.is_module() and
                callee_scope.base_name == 'append_worker' and
                ir.func.head().name == env.self_name and
                len(ir.func.qualified_symbol) > 2):
            _, arg = ir.args[0]
            worker_scope = arg.symbol.typ.scope
            if worker_scope.is_method():
                new_arg = self._make_new_worker(arg)
                assert self.scope.parent.is_module()
                append_worker_sym = self.scope.parent.find_sym('append_worker')
                assert append_worker_sym
                self_var = TEMP(ir.func.head(), Ctx.LOAD)
                new_func = ATTR(self_var, append_worker_sym, Ctx.LOAD)
                ir.func = new_func
                ir.args[0] = (None, new_arg)
            else:
                assert self.scope.parent.is_module()
                append_worker_sym = self.scope.parent.find_sym('append_worker')
                assert append_worker_sym
                self_var = TEMP(ir.func.head(), Ctx.LOAD)
                new_func = ATTR(self_var, append_worker_sym, Ctx.LOAD)
                ir.func = new_func
                ir.args[0] = (None, arg)
        else:
            super().visit_CALL(ir)

    def visit_TEMP(self, ir):
        sym_t = ir.symbol.typ
        if not sym_t.is_function():
            return
        sym_scope = sym_t.scope
        if not sym_scope.is_closure() and not sym_scope.is_assigned():
            return
        if sym_scope.is_method() and sym_scope.parent is not self.scope.parent:
            self._make_new_assigned_method(ir, sym_scope)

    def visit_ATTR(self, ir):
        attr_t = ir.symbol.typ
        if not attr_t.is_function():
            return
        sym_scope = attr_t.scope
        if not sym_scope.is_closure() and not sym_scope.is_assigned():
            return
        if sym_scope.is_method() and sym_scope.parent is not self.scope.parent:
            self._make_new_assigned_method(ir, sym_scope)

    def _make_new_worker(self, arg):
        parent_module = self.scope.parent
        worker_scope = arg.symbol.typ.scope
        inst_name = arg.tail().name
        new_worker = worker_scope.clone(inst_name, str(worker_scope.instance_number()), parent=parent_module)
        if new_worker.is_inlinelib():
            new_worker.del_tag('inlinelib')
        worker_self = new_worker.find_sym('self')
        worker_self.typ = worker_self.typ.clone(scope=parent_module)
        in_self = new_worker.param_symbols(with_self=True)[0]
        in_self.typ = in_self.typ.clone(scope=parent_module)
        new_exp = arg.exp.clone()
        ctor_self = self.scope.find_sym('self')
        new_exp.replace(ctor_self, worker_self)

        attr_map = {worker_self:new_exp}
        sym_replacer = SymbolReplacer(sym_map={}, attr_map=attr_map)
        sym_replacer.process(new_worker, new_worker.entry_block)
        UseDefDetector().process(new_worker)

        new_worker_sym = parent_module.add_sym(new_worker.base_name,
                                               typ=Type.function(new_worker))
        arg.exp = TEMP(ctor_self, Ctx.LOAD)
        arg.symbol = new_worker_sym
        self.driver.insert_scope(new_worker)

        scope_map = {worker_scope:new_worker}
        children = [c for c in worker_scope.collect_scope() if c.is_closure()]
        for child in children:
            new_child = worker_scope._clone_child(new_worker, worker_scope, child)
            scope_map[child] = new_child
            self.driver.insert_scope(new_child)
            sym_replacer.process(new_child, new_child.entry_block)
            UseDefDetector().process(new_child)
        for old, new in scope_map.items():
            syms = new_worker.find_scope_sym(old)
            for sym in syms:
                if sym.scope in scope_map.values():
                    sym.typ = sym.typ.clone(scope=new)
        return arg

    def _make_new_assigned_method(self, arg, assigned_scope):
        module_scope = self.scope.parent
        new_method = assigned_scope.clone('', '', parent=module_scope)
        if new_method.is_inlinelib():
            new_method.del_tag('inlinelib')
        self_sym = new_method.find_sym('self')
        self_sym.typ = self_sym.typ.clone(scope=module_scope)

        in_self = new_method.param_symbols(with_self=True)[0]
        in_self.typ = in_self.typ.clone(scope=module_scope)
        new_exp = arg.exp.clone()
        ctor_self = self.scope.find_sym('self')
        new_exp.replace(ctor_self, self_sym)

        attr_map = {self_sym:new_exp}
        sym_replacer = SymbolReplacer(sym_map={}, attr_map=attr_map)
        sym_replacer.process(new_method, new_method.entry_block)
        UseDefDetector().process(new_method)

        new_method_sym = module_scope.add_sym(new_method.base_name,
                                              typ=Type.function(new_method))
        arg.exp = TEMP(ctor_self, Ctx.LOAD)
        arg.symbol = new_method_sym
        self.driver.insert_scope(new_method)


class ObjectHierarchyCopier(object):
    def __init__(self):
        pass

    def _is_inlining_object(self, ir):
        return (ir.is_a([TEMP, ATTR]) and
                not ir.symbol.is_param() and
                ir.symbol.typ.is_object() and
                ir.symbol.typ.scope and
                not ir.symbol.typ.scope.is_module())

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
            class_scope = cp.src.symbol.typ.scope
            assert class_scope.is_assignable(cp.dst.symbol.typ.scope)
            for sym in class_scope.class_fields().values():
                if not sym.typ.is_object():
                    continue
                new_dst = ATTR(cp.dst.clone(), sym, Ctx.STORE)
                new_src = ATTR(cp.src.clone(), sym, Ctx.LOAD)
                new_cp = MOVE(new_dst, new_src)
                new_cp.loc = cp.loc
                cp_idx = cp.block.stms.index(cp)
                cp.block.insert_stm(cp_idx + 1, new_cp)
                if sym.typ.is_object():
                    worklist.append(new_cp)


class SpecializeWorker(IRTransformer):
    '''
    Specialize Worker with object type argument
    '''
    def process(self, scope):
        self.new_workers = []
        super().process(scope)
        return self.new_workers

    def visit_EXPR(self, ir):
        if ir.exp.is_a(CALL):
            callee_scope = ir.exp.callee_scope
            if (callee_scope.is_method()
                    and callee_scope.parent.is_module()
                    and callee_scope.base_name == 'append_worker'):
                self._specialize_worker(ir.exp)
        self.new_stms.append(ir)

    def _specialize_worker(self, call):
        has_object_arg = False
        for name, arg in call.args:
            if arg.is_a([TEMP, ATTR]):
                arg_t = arg.symbol.typ
                if arg_t.is_object():
                    has_object_arg = True
                    break
        if not has_object_arg:
            return
        arg1_t = call.args[0][1].symbol.typ
        origin_worker = arg1_t.scope
        new_worker = self._make_new_worker(origin_worker, call.args)
        args = []
        if origin_worker.is_method():
            param_symbols = new_worker.param_symbols(with_self=True)
        else:
            param_symbols = [None] + new_worker.param_symbols()

        for pindex, ((name, arg), sym) in enumerate(zip(call.args, param_symbols)):
            if (arg.is_a([TEMP, ATTR])
                    and arg.symbol.typ.is_object()):
                if arg.is_a(TEMP):
                    fail(self.current_stm, Errors.WORKER_TEMP_OBJ_ARG)
                self._subst_obj_arg(new_worker, arg, sym)
                new_worker.remove_param(sym)
            else:
                args.append((name, arg))
        call.args[:len(params)] = args[:]

    def _subst_obj_arg(self, new_worker, arg, param):
        param_sym, _, _ = param
        assert arg.is_a(ATTR)
        assert arg.head().is_self()
        assert new_worker.parent.is_module()
        if arg.exp.is_a(ATTR):
            arg = arg.clone()
            arg.replace_head(new_worker.find_sym('self'))
            rep_ir = arg
        else:
            assert arg.exp.is_a(TEMP)
            rep_ir = ATTR(TEMP(new_worker.find_sym('self'), Ctx.LOAD),
                          arg.symbol, Ctx.LOAD)
        sym_replacer = SymbolReplacer(sym_map={param_sym:rep_ir}, attr_map={})
        sym_replacer.process(new_worker, new_worker.entry_block)

    def _make_new_worker(self, worker, args):
        parent_module = self.scope.parent
        new_worker = worker.clone('', str(worker.instance_number()), parent=parent_module)
        if new_worker.is_inlinelib():
            new_worker.del_tag('inlinelib')
        # Convert function worker to method of module
        if not new_worker.is_method():
            new_worker.add_tag('method')
            new_worker_self = new_worker.add_sym('self',
                                                 tags={'self'},
                                                 typ=Type.object(parent_module))
            new_worker.add_param(new_worker_self, new_worker_self, None)
        # transform append_worker call
        ctor_self = self.scope.find_sym('self')
        new_worker_sym = parent_module.add_sym(new_worker.base_name,
                                               typ=Type.function(new_worker))
        worker_attr = ATTR(TEMP(ctor_self, Ctx.LOAD), new_worker_sym, Ctx.LOAD)
        args[0] = (args[0][0], worker_attr)

        self.new_workers.append(new_worker)
        return new_worker
