from collections import defaultdict, deque
from collections.abc import Iterable
from typing import cast
from ..block import Block
from ..irvisitor import IRVisitor, IRTransformer
from ..ir import Ctx, IR, IRExp, IRNameExp, IRVariable, IRCallable, IRStm, CONST, UNOP, TEMP, ATTR, CALL, NEW, SYSCALL, MOVE, EXPR, RET, JUMP
from ..irhelper import qualified_symbols, qsym2var, irexp_type
from ..scope import Scope
from ..symbol import Symbol
from ..synth import merge_synth_params
from ..types.type import Type
from ..types import typehelper
from ..analysis.usedef import UseDefDetector
from ...common.env import env
from ...common.common import fail
from ...common.errors import Errors
import logging
logger = logging.getLogger()

type SymbolMap = dict[Symbol, Symbol|IRExp]
type AttributeMap = dict[Symbol, IRExp]
type ReplaceMap = dict[Symbol, IRExp]
type CallStmPair = tuple[IRCallable, IRStm]

class CallerScope(Scope):
    pass

class CalleeScope(Scope):
    pass

type CallsDict = dict[CalleeScope, list[CallStmPair]]
type Callgraph = dict[CallerScope, CallsDict]

class InlineOpt(object):
    inline_counts = 0

    def __init__(self):
        self.new_scopes = []

    def process_all(self, driver):
        self.processed_scopes = set()
        self.process_scopes(driver.current_scopes)

    def process_scopes(self, scopes):
        call_graph: Callgraph = self._build_call_graph(scopes)
        callers = set()
        while call_graph:
            leaf = self._pop_leaf(call_graph)
            if not leaf:
                continue
            caller, callee, call_irs = leaf
            if callee.is_method():
                self._process_method(caller, callee, call_irs)
            else:
                self._process_func(caller, callee, call_irs)
            logger.debug(f"inlined {callee.name} on {caller.name}")
            # logger.debug(scope)
            callers.add(caller)
        for c in callers:
            self._reduce_useless_move(c)

    def _build_call_graph(self, scopes: list[Scope]) -> Callgraph:
        call_graph: Callgraph = {}
        for scope in scopes:
            self._build_call_graph_rec(cast(CallerScope, scope), call_graph)
        return call_graph

    def _build_call_graph_rec(self, caller: CallerScope, call_graph: Callgraph):
        if caller in call_graph:
            return
        calls:CallsDict = defaultdict(list)
        collector = CallCollector(calls)
        collector.process(caller)
        if calls:
            call_graph[caller] = calls
            for callee in calls.keys():
                self._build_call_graph_rec(cast(CallerScope, callee), call_graph)

    def _pop_leaf(self, call_graph: Callgraph) -> tuple[CallerScope, CalleeScope, list[CallStmPair]] | None:
        '''Find leaf node (that are not called by other node) in the callgraph and return them one by one'''
        for caller, calls in call_graph.copy().items():
            for callee in calls.copy().keys():
                if callee not in call_graph:
                    call_irs = calls.pop(callee)
                    if not calls:
                        call_graph.pop(caller)
                    if callee.is_lib() or callee.is_pure():
                        continue
                    return caller, callee, call_irs
        return None

    def _make_replace_args_map(self, callee: CalleeScope, call: IRCallable) -> ReplaceMap:
        '''Make argument-parameter map for replacing parameters of the callee'''
        arg_map: ReplaceMap = {}
        for i, (param, defval) in enumerate(zip(callee.param_symbols(), callee.param_default_values())):
            if len(call.args) > i:
                _, arg = call.args[i]
            else:
                arg = cast(IRExp, defval)
            if isinstance(arg, (TEMP, ATTR, CONST, UNOP)):
                arg_map[param] = arg
            else:
                assert False, 'CALL is not quadruple form'
        return arg_map

    def _make_replace_self_obj_map(self, callee: CalleeScope, call: IRCallable, call_stm: IRStm, caller: CallerScope) -> ReplaceMap:
        '''Make 'self'-object map for replacing 'self' of the callee method'''
        self_map: ReplaceMap = {}
        callee_self = callee.find_sym(env.self_name)
        assert callee_self
        if callee.is_ctor():
            assert not callee.is_returnable()
            if isinstance(call_stm, MOVE):
                assert call_stm.src == call
                qsym = cast(tuple[Symbol, ...], qualified_symbols(call_stm.dst, caller))
                assert all(isinstance(sym, Symbol) for sym in qsym)
                self_map[callee_self] = qsym2var(qsym, Ctx.LOAD)
            else:
                logger.error(f"cannot inline {callee.name} because of statement is not MOVE")
        else:
             assert isinstance(call.func, ATTR)
             receiver_sym = cast(tuple[Symbol, ...], qualified_symbols(call.func.exp, caller))
             self_map[callee_self] = qsym2var(receiver_sym, Ctx.LOAD)
        return self_map

    def _rename(self, callee: CalleeScope, caller: CallerScope):
        '''Make all local names used in the callee unique (so that they do not match the names in the caller)'''
        caller_name_exps = LocalVariableCollector().process(caller)
        caller_names = set([name_exp.name for name_exp in caller_name_exps])
        caller_names |= {'@return'}

        callee_name_exps = LocalVariableCollector().process(callee)
        name_ir_map: dict[str, list[IRNameExp]] = defaultdict(list)
        for name_exp in callee_name_exps:
            name_ir_map[name_exp.name].append(name_exp)

        for name, name_exps in name_ir_map.items():
            sym = callee.find_sym(name)
            assert isinstance(sym, Symbol)
            # Variable 'self' is not renamed because it is referenced by a fixed name (env.self_name)
            # by _make_replace_self_obj_map to replace it in the inlining process
            if sym.is_self():
                continue
            if sym.is_builtin():
                continue
            if name in caller_names:
                count = 0
                new_name = f'{name}_{count}'
                while new_name in caller_names or new_name in name_ir_map.keys():
                    count += 1
                    new_name = f'{name}_{count}'
                if callee.has_sym(name):
                    callee.rename_sym(name, new_name)
                for name_exp in name_exps:
                    name_exp.name = new_name

    def _merge_symbols(self, callee: CalleeScope, caller: CallerScope):
        callee_name_exps = LocalVariableCollector().process(callee)
        callee_names = set([name_exp.name for name_exp in callee_name_exps])
        for name in callee_names:
            sym = callee.find_sym(name)
            if sym and not caller.has_sym(name):
                caller.add_sym(name, sym.tags, sym.typ)

    def _merge_children(self, callee: CalleeScope, caller: CallerScope):
        caller.children.extend(callee.children)

    def _clone_callee(self, caller: CallerScope, callee: CalleeScope) -> CalleeScope:
        callee_clone : CalleeScope = cast(CalleeScope, callee.clone('', '#clone', parent=callee.parent, recursive=True))
        return callee_clone

    def _removet_closure_if_needed(self, caller: CallerScope):
        assert caller.is_enclosure()
        caller_name_exps = LocalVariableCollector().process(caller)
        has_reference = False
        orig_closures = caller.closures.copy()
        for clos in orig_closures:
            for name_exp in caller_name_exps:
                if name_exp.name == clos.base_name:
                    has_reference = True
                    break
            else:
                caller.closures.remove(clos)
                Scope.destroy(clos)
                caller.del_sym(clos.base_name)
        if not has_reference:
            caller.del_tag('enclosure')
            for sym in caller.symbols.values():
                if sym.is_free():
                    sym.del_tag('free')
            assert not caller.closures

    def _process_func(self, caller: CallerScope, callee: CalleeScope, call_irs: list[CallStmPair]):
        if callee.is_testbench():
            return
        if not env.config.perfect_inlining:
            if caller.is_testbench() and callee.is_function_module():
                return
        for call, call_stm in call_irs:
            self.inline_counts += 1
            callee_clone : CalleeScope = self._clone_callee(caller, callee)
            self._rename(callee_clone, caller)
            # replace args and return
            replace_arg_map = self._make_replace_args_map(callee_clone, call)
            replace_map = replace_arg_map
            IRReplacer(replace_map).process(callee_clone, callee_clone.entry_block)
            if callee.is_returnable():
                self._replace_result_exp(call_stm, call, callee_clone)
            self._merge_symbols(callee_clone, caller)
            self._merge_children(callee_clone, caller)
            # make block clones on caller scope
            block_map, _ = callee_clone.clone_blocks(caller)
            callee_entry_blk = block_map[callee_clone.entry_block]
            callee_exit_blk = block_map[callee_clone.exit_block]
            assert len(callee_exit_blk.succs) <= 1
            self._merge_blocks(call_stm, callee.is_ctor(), callee_entry_blk, callee_exit_blk)

            if isinstance(call_stm, EXPR):
                call_stm.block.stms.remove(call_stm)

            if caller.is_enclosure():
                self._removet_closure_if_needed(caller)

            Scope.destroy(callee_clone)
            callee_clone.parent.del_sym(callee_clone.base_name)

    def _process_method(self, caller: CallerScope, callee: CalleeScope, call_irs: list[CallStmPair]):
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
            callee_clone : CalleeScope = cast(CalleeScope, callee.clone('', '#clone', parent=callee.parent))
            self._rename(callee_clone, caller)
            # replace args, return and 'self'
            replace_arg_map = self._make_replace_args_map(callee_clone, call)
            replace_self_map = self._make_replace_self_obj_map(callee_clone, call, call_stm, caller)
            replace_map = replace_arg_map | replace_self_map
            IRReplacer(replace_map).process(callee_clone, callee_clone.entry_block)
            if callee.is_returnable():
                self._replace_result_exp(call_stm, call, callee_clone)

            self._merge_symbols(callee_clone, caller)
            self._merge_children(callee_clone, caller)
            # make block clones on caller scope
            block_map, _ = callee_clone.clone_blocks(caller)
            callee_entry_blk = block_map[callee_clone.entry_block]
            callee_exit_blk = block_map[callee_clone.exit_block]
            assert len(callee_exit_blk.succs) <= 1
            self._merge_blocks(call_stm, callee.is_ctor(), callee_entry_blk, callee_exit_blk)

            if isinstance(call_stm, MOVE) and callee.is_ctor():
                assert call_stm.src == call
                builtin_new = SYSCALL(TEMP('$new'),
                                      args=[('typ', call.func.clone(ctx=Ctx.LOAD))],
                                      kwargs={})
                call_stm.replace(call_stm.src, builtin_new)
            elif isinstance(call_stm, EXPR):
                call_stm.block.stms.remove(call_stm)

            if caller.is_enclosure():
                self._removet_closure_if_needed(caller)

            Scope.destroy(callee_clone)

    def _replace_result_exp(self, call_stm: IRStm, call: IRCallable, callee: CalleeScope):
        '''Finds the '@return' symbol (already renamed) of the callee and replace the call expression of the caller statement'''
        syms = callee.find_syms_by_tags({'return'})
        assert len(syms) == 1
        result_sym = syms.pop()
        result_sym.del_tag('return')
        result = TEMP(result_sym.name)
        match call_stm:
            case MOVE() as move:
                assert move.src == call
                move.src = result
            case EXPR() as expr:
                assert expr.exp == call
                expr.exp = result

    def _merge_blocks(self, call_stm: IRStm, is_ctor: bool, callee_entry_blk: Block, callee_exit_blk: Block):
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

        if callee_exit_blk.stms and isinstance(callee_exit_blk.stms[-1], RET):
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

    def _reduce_useless_move(self, scope: Scope):
        for block in scope.traverse_blocks():
            removes = []
            for stm in block.stms:
                match stm:
                    case MOVE(dst=TEMP(), src=TEMP()) if stm.dst.name == cast(TEMP, stm.src).name:
                        removes.append(stm)
            for rm in removes:
                block.stms.remove(rm)


class CallCollector(IRVisitor):
    def __init__(self, calls: CallsDict):
        super().__init__()
        self.calls = calls

    def visit_CALL(self, ir):
        callee_scope = ir.get_callee_scope(self.scope)
        self.calls[callee_scope].append((ir, self.current_stm))

    def visit_NEW(self, ir):
        callee_scope = ir.get_callee_scope(self.scope)
        assert callee_scope.is_class()
        ctor = callee_scope.find_ctor()
        assert ctor
        self.calls[ctor].append((ir, self.current_stm))


class LocalVariableCollector(IRVisitor):
    def __init__(self):
        super().__init__()
        self.local_vars = []

    def process(self, scope):
        super().process(scope)
        return self.local_vars

    def visit_TEMP(self, ir):
        sym = self.scope.find_sym(ir.name)
        if sym and sym.scope is self.scope:
            self.local_vars.append(ir)

    def visit_ATTR(self, ir):
        self.visit(ir.exp)


class IRReplacer(IRTransformer):
    def __init__(self, replace_map: ReplaceMap):
        super().__init__()
        self.replace_map = replace_map

    def process(self, scope, entry_block):
        self.scope = scope
        for blk in self._traverse_blocks(entry_block):
            self._process_block(blk)

    def _traverse_blocks(self, entry_block):
        assert len(entry_block.preds) == 0
        yield from entry_block.traverse()

    def visit_TEMP(self, ir):
        ret_ir = ir
        sym = self.scope.find_sym(ir.name)
        assert sym
        if sym in self.replace_map:
            attr = self.replace_map[sym].clone(ctx=ir.ctx)
            ret_ir = attr
        if isinstance(ret_ir, IRVariable):
            ret_sym = qualified_symbols(ret_ir, self.scope)[-1]
            if isinstance(ret_sym, Symbol):
                for expr in typehelper.find_expr(ret_sym.typ):
                    assert isinstance(expr, EXPR)
                    old_stm = self.current_stm
                    self.current_stm = expr
                    self.visit(expr)
                    self.current_stm = old_stm
        return ret_ir

    def visit_ATTR(self, ir):
        exp = self.visit(ir.exp)
        if exp:
            ir.exp = exp
        sym = qualified_symbols(ir, self.scope)[-1]
        if isinstance(sym, Symbol):
            for expr in typehelper.find_expr(sym.typ):
                assert isinstance(expr, EXPR)
                old_stm = self.current_stm
                self.current_stm = expr
                self.visit(expr)
                self.current_stm = old_stm
        return ir

    def visit_ARRAY(self, ir):
        self.visit(ir.repeat)
        for item in ir.items:
            self.visit(item)
        return ir


class SymbolReplacer(IRVisitor):
    def __init__(self, sym_map: SymbolMap, attr_map: AttributeMap, inst_name=None):
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
            return TEMP(qsym[0].name, ctx)
        else:
            exp = self._qsym_to_var(qsym[:-1], Ctx.LOAD)
            return ATTR(exp, qsym[-1].name, ctx)

    def visit_TEMP(self, ir):
        ret_ir = ir
        sym = self.scope.find_sym(ir.name)
        assert sym
        if self.attr_map and sym in self.attr_map:
            attr = self.attr_map[sym].clone()
            ret_ir = attr
        elif sym in self.sym_map:
            rep = self.sym_map[sym]
            if isinstance(rep, Symbol):
                ir.name = rep.name
                ret_ir = ir
            elif isinstance(rep, tuple):  # qualified_symbol
                ret_ir = self._qsym_to_var(rep, ir.ctx)
            else:
                assert isinstance(rep, IRExp)
                self.current_stm.replace(ir, rep)
                ret_ir = rep
        if ret_ir.is_a(IRVariable):
            ret_sym = qualified_symbols(cast(IRVariable, ret_ir), self.scope)[-1]
            assert isinstance(ret_sym, Symbol)
            for expr in typehelper.find_expr(ret_sym.typ):
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
        sym = qualified_symbols(ir, self.scope)[-1]
        assert isinstance(sym, Symbol)
        if sym in self.sym_map:
            new_sym = self.sym_map[sym]
            assert isinstance(new_sym, Symbol)
            ir.name = new_sym.name
        for expr in typehelper.find_expr(sym.typ):
            assert expr.is_a(EXPR)
            old_stm = self.current_stm
            self.current_stm = expr
            self.visit(expr)
            self.current_stm = old_stm

    def visit_ARRAY(self, ir):
        self.visit(ir.repeat)
        for item in ir.items:
            self.visit(item)


class FlattenFieldAccess(IRTransformer):
    def _make_flatname(self, qsym):
        qnames = [sym.name for sym in qsym if sym.name != env.self_name]
        return '_'.join(qnames)

    def _make_flatten_qsym(self, ir):
        assert isinstance(ir, ATTR)
        flatname = None
        qsyms = qualified_symbols(ir, self.scope)
        head = qsyms[0]
        inlining_scope = head.scope
        if qsyms[-1].typ.is_function():
            tail = (qsyms[-1], )
            qsyms = qsyms[:-1]
        else:
            tail = tuple()

        ancestor = qsyms[-1]
        for i, sym in enumerate(qsyms):
            if (sym.typ.is_object() and not sym.is_subobject() and
                    sym.typ.scope.is_module()):
                flatname = self._make_flatname(qsyms[i + 1:])
                head = qsyms[:i + 1]
                scope = sym.typ.scope
                break
        else:
            flatname = self._make_flatname(qsyms)
            head = tuple()
            scope = inlining_scope
        if flatname:
            if scope.has_sym(flatname):
                flatsym = scope.find_sym(flatname)
            else:
                tags = set()
                qsym = qualified_symbols(ir, self.scope)
                for sym in qsym:
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
        newir = TEMP(qsym[0].name, context(0))
        for i in range(1, len(qsym)):
            newir = ATTR(newir, qsym[i].name, context(i))
        assert newir.ctx == ir.ctx
        return newir

    def visit_TEMP(self, ir):
        sym = self.scope.find_sym(ir.name)
        assert sym
        for expr in typehelper.find_expr(sym.typ):
            assert isinstance(expr, EXPR)
            old_stm = self.current_stm
            self.current_stm = expr
            expr.exp = self.visit(expr.exp)
            self.current_stm = old_stm
        return ir

    def visit_ATTR(self, ir):
        qsym = qualified_symbols(ir, self.scope)
        sym = qsym[-1]
        assert isinstance(sym, Symbol)
        for expr in typehelper.find_expr(sym.typ):
            assert isinstance(expr, EXPR)
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
        receiver_t = qsym[-2].typ
        if not receiver_t.is_object():
            return ir
        object_scope = receiver_t.scope
        if object_scope.is_module():
            return ir
        if object_scope.is_port():
            return ir

        qsym = self._make_flatten_qsym(ir)
        newattr = self._make_new_ATTR(qsym, ir)  # TODO: use qsym2var
        return newattr


class FlattenObjectArgs(IRTransformer):
    def __init__(self):
        self.params_modified_scopes = set()

    def visit_EXPR(self, ir):
        if isinstance(ir.exp, CALL):
            callee_scope = ir.exp.get_callee_scope(self.scope)
            if (callee_scope.is_method()
                    and callee_scope.parent.is_module()
                    and callee_scope.base_name == 'append_worker'):
                self._flatten_args(ir.exp)
        self.new_stms.append(ir)

    def _flatten_args(self, call):
        args = []
        for pindex, (name, arg) in enumerate(call.args):
            if isinstance(arg, IRVariable):
                arg_sym = qualified_symbols(arg, self.scope)[-1]
                assert isinstance(arg_sym, Symbol)
            else:
                arg_sym = None
            if (arg_sym
                    and arg_sym.typ.is_object()
                    and not arg_sym.typ.scope.is_port()):
                flatten_args = self._flatten_object_args(call, arg, pindex - 1)
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
                    new_sym = module_scope.add_sym(new_name, tags=set(), typ=fsym.typ)
                new_arg = arg.clone()
                new_arg.symbol = new_sym
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
            #    param_copy = worker_scope.add_sym(new_name, tags=set(), typ=sym.typ)
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
        callee_scope = ir.get_callee_scope(self.scope)
        if (callee_scope.is_method() and
                callee_scope.parent.is_module() and
                callee_scope.base_name == 'append_worker' and
                ir.func.head_name() == env.self_name and
                len(ir.func.qualified_name) > 2):
            _, arg = ir.args[0]
            arg_t = irexp_type(arg, self.scope)
            worker_scope = arg_t.scope
            if worker_scope.is_method():
                new_worker, new_arg = self._make_new_worker(arg)
                new_worker.parent.register_worker(new_worker, ir.args)
                assert self.scope.parent.is_module()
                append_worker_sym = self.scope.parent.find_sym('append_worker')
                assert append_worker_sym
                qsyms = qualified_symbols(ir.func, self.scope)
                func_head = qsyms[0]
                self_var = TEMP(func_head.name)
                new_func = ATTR(self_var, append_worker_sym.name)
                ir.func = new_func
                ir.args[0] = (None, new_arg)
            else:
                assert self.scope.parent.is_module()
                append_worker_sym = self.scope.parent.find_sym('append_worker')
                assert append_worker_sym
                qsyms = qualified_symbols(ir.func, self.scope)
                func_head = qsyms[0]
                self_var = TEMP(func_head.name)
                new_func = ATTR(self_var, append_worker_sym.name)
                ir.func = new_func
                ir.args[0] = (None, arg)
        else:
            super().visit_CALL(ir)

    def visit_TEMP(self, ir):
        sym_t = irexp_type(ir, self.scope)
        if not sym_t.is_function():
            return
        sym_scope = sym_t.scope
        if not sym_scope.is_closure() and not sym_scope.is_assigned():
            return
        if sym_scope.is_method() and sym_scope.parent is not self.scope.parent:
            self._make_new_assigned_method(ir, sym_scope)

    def visit_ATTR(self, ir):
        attr_t = irexp_type(ir, self.scope)
        if not attr_t.is_function():
            return
        sym_scope = attr_t.scope
        if not sym_scope.is_closure() and not sym_scope.is_assigned():
            return
        if sym_scope.is_method() and sym_scope.parent is not self.scope.parent:
            self._make_new_assigned_method(ir, sym_scope)

    def _make_new_worker(self, arg):
        parent_module = self.scope.parent
        qsym = qualified_symbols(arg, self.scope)
        arg_sym = qsym[-1]
        assert isinstance(arg_sym, Symbol)
        arg_t = arg_sym.typ
        worker_scope = arg_t.scope
        assert isinstance(arg, ATTR)
        inst_name = arg.exp.name
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

        # TODO: check
        assert False
        attr_map = {worker_self:new_exp}
        sym_replacer = SymbolReplacer(sym_map={}, attr_map=attr_map)
        sym_replacer.process(new_worker, new_worker.entry_block)
        UseDefDetector().process(new_worker)

        new_worker_sym = parent_module.add_sym(new_worker.base_name,
                                               tags=set(),
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
        return new_worker, arg

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

        # TODO: check
        assert False
        attr_map = {self_sym:new_exp}
        sym_replacer = SymbolReplacer(sym_map={}, attr_map=attr_map)
        sym_replacer.process(new_method, new_method.entry_block)
        UseDefDetector().process(new_method)

        new_method_sym = module_scope.add_sym(new_method.base_name,
                                              tags=set(),
                                              typ=Type.function(new_method))
        arg.exp = TEMP(ctor_self, Ctx.LOAD)
        arg.symbol = new_method_sym
        self.driver.insert_scope(new_method)


class ObjectHierarchyCopier(object):
    def __init__(self):
        pass

    def _is_inlining_object(self, ir):
        if isinstance(ir, IRVariable):
            qsym = qualified_symbols(ir, self.scope)
            sym = qsym[-1]
            assert isinstance(sym, Symbol)
            return (not sym.is_param() and
                    sym.typ.is_object() and
                    sym.typ.scope and
                    not sym.typ.scope.is_module())
        else:
            return False

    def _is_object_copy(self, mov):
        return self._is_inlining_object(mov.src) and self._is_inlining_object(mov.dst)

    def _collect_object_copy(self):
        copies = []
        for block in self.scope.traverse_blocks():
            moves = [stm for stm in block.stms if isinstance(stm, MOVE)]
            copies.extend([stm for stm in moves if self._is_object_copy(stm)])
        return copies

    def process(self, scope):
        self.scope = scope
        copies = self._collect_object_copy()
        worklist = deque()
        worklist.extend(copies)
        while worklist:
            cp = worklist.popleft()
            src_sym = qualified_symbols(cp.src, self.scope)[-1]
            dst_sym = qualified_symbols(cp.dst, self.scope)[-1]
            assert isinstance(src_sym, Symbol)
            assert isinstance(dst_sym, Symbol)
            src_typ = src_sym.typ
            dst_typ = dst_sym.typ
            assert src_typ.has_scope()
            assert dst_typ.has_scope()
            class_scope = src_typ.scope
            assert class_scope.is_assignable(dst_typ.scope)
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
