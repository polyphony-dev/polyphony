"""Module instantiation and argument application using new IR.

CallCollector, new_find_called_module, ModuleInstantiator, ArgumentApplier
"""
from typing import cast
from ..irvisitor import IrVisitor
from ..ir import (
    IrExp, IrStm, IrVariable, IrCallable,
    Temp, Attr, Const, Call, SysCall, New,
    Move, Expr, Ctx, Array,
)
from ..irhelper import qualified_symbols
from ..scope import Scope, function2method
from ..symbol import Symbol
from ..types.type import Type
from ..analysis.usedef import UseDefDetector
from .varreplacer import VarReplacer
from .constopt import ConstantOpt
from ...common.env import env
import logging
logger = logging.getLogger()


def _get_callee_scope(ir, scope):
    """Resolve callee scope from a Call/New/SysCall node."""
    qsyms = qualified_symbols(ir.func, scope)
    symbol = qsyms[-1]
    assert isinstance(symbol, Symbol)
    func_t = symbol.typ
    assert func_t.has_scope()
    return func_t.scope


class CallCollector(IrVisitor):
    """Collect Call/New/SysCall nodes from IR."""

    def __init__(self):
        super().__init__()
        self.calls: list[tuple[Scope, IrStm, IrCallable]] = []

    def _process_block(self, block):
        for stm in block.stms:
            self.visit(stm)

    def process(self, scope):  # type: ignore[override]
        super().process(scope)
        return self.calls

    def visit_Call(self, ir):
        self.calls.append((self.scope, self.current_stm, ir))

    def visit_New(self, ir):
        self.calls.append((self.scope, self.current_stm, ir))

    def visit_SysCall(self, ir):
        if ir.name == '$new':
            self.calls.append((self.scope, self.current_stm, ir))


def new_find_called_module(scopes) -> list[tuple[Scope, Scope, Move]]:
    """Find module NEW calls from scopes using new IR CallCollector."""
    called_modules: list[tuple[Scope, Scope, Move]] = []
    calls: list[tuple[Scope, IrStm, IrCallable]] = []
    for s in scopes:
        calls.extend(CallCollector().process(s))
    for caller_scope, stm, call in calls:
        callee_scope = _get_callee_scope(call, caller_scope)
        if isinstance(stm, Move) and isinstance(call, New) and callee_scope.is_module():
            called_modules.append((callee_scope, caller_scope, cast(Move, stm)))
    return called_modules


class ModuleInstantiator(object):
    """Instantiate modules from NEW calls using new IR."""

    def process_modules(self, modules: list[tuple[Scope, Scope, Move]], names: list[str]):
        new_modules = []
        for (module, caller, move), name in zip(modules, names):
            if not name:
                name = f'{module.instance_number()}'
            new_module = module.instantiate(name, parent=module.parent)
            # If the module is imported from another namespace,
            # register the symbol at the import destination.
            new = cast(New, move.src)
            qsym = qualified_symbols(new.func, caller)
            func_sym = qsym[-1]
            assert isinstance(func_sym, Symbol)
            owner = caller.find_owner_scope(func_sym)
            if owner and func_sym.scope is not owner:
                asname = f'{new.name}_{name}'
                new_module_sym = new_module.parent.find_sym(new_module.base_name)
                owner.import_sym(new_module_sym, asname)

            self._process_workers(new_module)
            new_module.add_tag('instantiated')
            for s in new_module.collect_scope():
                s.add_tag('instantiated')
            new_modules.append(new_module)
            assert isinstance(move.src, New)
            new_src = new.subst(module.base_name, new_module.base_name)
            if new_src is not new:
                caller.find_block(move.block).replace_stm(move, move.model_copy(update={'src': new_src}))
        return new_modules

    def _process_workers(self, module):
        collector = CallCollector()
        ctor = module.find_ctor()
        calls = collector.process(ctor)
        origin_workers = set()
        for scope, stm, call in calls:
            callee_scope = _get_callee_scope(call, scope)
            if isinstance(call, Call) and callee_scope.base_name == 'append_worker':
                new_worker = self._instantiate_worker(call, stm, ctor, module, scope, origin_workers)
                module.register_worker(new_worker)
        # Remove origin workers
        for worker in origin_workers:
            Scope.destroy(worker)

    def _instantiate_worker(self, call, stm, ctor, module, scope, origin_workers):
        assert len(call.args) >= 1
        orig_call = call
        _, w = call.args[0]
        assert isinstance(w, IrVariable)
        w_sym = qualified_symbols(w, scope)[-1]
        assert isinstance(w_sym, Symbol)
        assert w_sym.typ.is_function()
        assert w_sym.typ.scope.is_worker()
        worker = w_sym.typ.scope
        origin_workers.add(worker)
        loop = False
        for i, (name, arg) in enumerate(call.args):
            if name == 'loop':
                assert isinstance(arg, Const) and isinstance(arg.value, bool)
                loop = arg.value
                call = call.model_copy(update={'args': call.args[:i] + call.args[i + 1:]})
                break

        if worker.is_instantiated():
            new_worker = worker
        else:
            # A worker is always a method of a module, even if it was just a function
            new_worker = worker.clone('', f'{worker.instance_number()}', parent=module, recursive=True)
            if new_worker.is_function():
                function2method(new_worker, module)
            assert new_worker.is_method()
        if loop:
            new_worker.add_tag('loop_worker')
        # Replace old worker references with new worker references
        if worker.is_method():
            new_call = call.subst(worker.base_name, new_worker.base_name)
        else:
            new_call = call.subst(w, Attr(name=new_worker.base_name, exp=Temp(name='self'), attr=new_worker.base_name, ctx=Ctx.LOAD))
        # Use orig_call for stm.subst since stm still references the original call
        new_stm = stm.subst(orig_call, new_call)
        if new_stm is not stm:
            scope.find_block(stm.block).replace_stm(stm, new_stm)
        new_worker.add_tag('instantiated')
        return new_worker




class ArgumentApplier(object):
    """Bind arguments to module/worker parameters using new IR."""

    def process_all(self):
        self._apply_api_params()
        scopes: list[Scope] = []
        top = Scope.global_scope()
        scopes = [top] + [s for s in top.children if s.is_testbench() and len(s.param_names()) == 0]
        while scopes:
            scopes = self.process_scopes(scopes)

    def process_scopes(self, scopes):
        calls: list[tuple[Scope, IrStm, IrCallable]] = []
        next_scopes = []
        for s in scopes:
            calls.extend(CallCollector().process(s))
        for scope, stm, call in calls:
            callee_scope = _get_callee_scope(call, scope)
            if isinstance(call, New) and callee_scope.is_module() and callee_scope.is_instantiated():
                ctor = callee_scope.find_ctor()
                assert ctor
                new_args = self._bind_args(scope, call.args, ctor)
                if new_args is not call.args:
                    new_call = call.model_copy(update={'args': new_args})
                    new_stm = stm.subst(call, new_call)
                    if new_stm is not stm:
                        scope.find_block(stm.block).replace_stm(stm, new_stm)
                next_scopes.append(ctor)
            elif isinstance(call, Call) and callee_scope.base_name == 'append_worker':
                assert len(call.args) >= 1
                _, w = call.args[0]
                assert isinstance(w, IrVariable)
                w_sym = qualified_symbols(w, scope)[-1]
                assert isinstance(w_sym, Symbol)
                assert w_sym.typ.is_function()
                assert w_sym.typ.scope.is_worker()
                worker = w_sym.typ.scope
                worker_args = call.args[1:]
                new_worker_args = self._bind_args(scope, worker_args, worker)
                if new_worker_args is not worker_args:
                    new_call = call.model_copy(update={'args': (call.args[0],) + new_worker_args})
                    new_stm = stm.subst(call, new_call)
                    if new_stm is not stm:
                        scope.find_block(stm.block).replace_stm(stm, new_stm)
        return next_scopes

    def _value_to_ir(self, value) -> IrExp:
        """Convert a Python value to an IR expression node."""
        if isinstance(value, int):
            return Const(value=value)
        elif isinstance(value, type):
            return Temp(name=value.__name__)
        elif callable(value):
            return Temp(name=value.__name__)
        elif isinstance(value, (tuple, list)):
            items = tuple(self._value_to_ir(v) for v in value)
            return Array(items=items, mutable=isinstance(value, list))
        else:
            return Const(value=value)

    def _apply_api_params(self):
        """Bind params from compile() API (env.targets with dict params)."""
        if not env.targets:
            return
        all_scopes = Scope.get_scopes(with_global=False, with_class=True)
        for target_entry in env.targets:
            if not isinstance(target_entry, tuple) or len(target_entry) != 2:
                continue
            target_name, params = target_entry
            if not isinstance(params, dict) or not params:
                continue
            # Find the target scope by name
            callee = None
            for s in all_scopes:
                if s.orig_base_name == target_name:
                    if s.is_module():
                        callee = s.find_ctor()
                    elif s.is_function() or s.is_worker():
                        callee = s
                    break
            if callee is None:
                continue
            # Build binding list from params dict
            param_names = callee.param_names()
            binding: list[tuple[int, IrExp]] = []
            for i, pname in enumerate(param_names):
                if pname in params:
                    binding.append((i, self._value_to_ir(params[pname])))
            if not binding:
                continue
            bound_indices = {i for i, _ in binding}
            # Apply bindings (same logic as _bind_args core)
            for i, arg in binding:
                pname = callee.param_symbols()[i].name
                VarReplacer.replace_uses(callee, Temp(name=pname), arg)
            callee.remove_param([i for i, _ in binding])
            ConstantOpt().process(callee)
            if callee.is_ctor():
                callee.parent.set_bound_args(binding)
            # Update call sites in testbenches to remove the bound arguments
            top = Scope.global_scope()
            tb_scopes = [top] + [s for s in top.children if s.is_testbench()]
            for tb in tb_scopes:
                for scope, stm, call in CallCollector().process(tb):
                    if not isinstance(call, (Call, New)):
                        continue
                    try:
                        callee_scope = _get_callee_scope(call, scope)
                    except (AssertionError, IndexError):
                        continue
                    target_scope = callee_scope.find_ctor() if callee_scope.is_module() else callee_scope
                    if target_scope is not callee:
                        continue
                    new_args = tuple(a for j, a in enumerate(call.args) if j not in bound_indices)
                    if new_args != call.args:
                        new_call = call.model_copy(update={'args': new_args})
                        new_stm = stm.subst(call, new_call)
                        if new_stm is not stm:
                            scope.find_block(stm.block).replace_stm(stm, new_stm)

    def _resolve_seq_arg(self, arg: IrExp, caller_scope: Scope) -> IrExp:
        """Resolve a seq-typed arg to its Array when it was converted to an integer ID."""
        if isinstance(arg, Const) and isinstance(arg.value, int):
            array = env.seq_id_to_array.get(arg.value)
            if array is not None:
                return array.clone()
        elif isinstance(arg, IrVariable):
            usedef = UseDefDetector().process(caller_scope)
            qsym = qualified_symbols(arg, caller_scope)
            defs = list(usedef.get_stms_defining(qsym))
            if len(defs) == 1 and isinstance(defs[0], Move) and isinstance(defs[0].src, Array):
                return defs[0].src.model_copy(deep=True)
        return arg

    def _import_arg_symbols(self, arg: IrExp, caller_scope: Scope, callee: Scope):
        """Import symbols referenced by arg from caller_scope into callee."""
        if isinstance(arg, Temp):
            sym = caller_scope.find_sym(arg.name)
            if sym and not callee.find_sym(arg.name):
                callee.import_sym(sym)
        elif isinstance(arg, Attr):
            for name in arg.qualified_name:
                sym = caller_scope.find_sym(name)
                if sym and not callee.find_sym(name):
                    callee.import_sym(sym)

    def _bind_args(self, caller_scope: Scope, args: tuple[tuple[str, IrExp], ...], callee: Scope):
        """Bind arguments to callee parameters. Returns new args tuple with bound args removed."""
        binding: list[tuple[int, IrExp]] = []
        module_param_vars: list[tuple[str, IrExp]] = []
        param_names = callee.param_names()
        param_syms = callee.param_symbols()
        for i, (_, arg) in enumerate(args):
            if isinstance(arg, IrExp):
                if param_names[i].isupper():
                    module_param_vars.append((param_names[i], arg))
                else:
                    # Resolve seq-typed args (tuple/list) that were converted to integer IDs
                    if i < len(param_syms) and param_syms[i].typ.is_seq():
                        arg = self._resolve_seq_arg(arg, caller_scope)
                    binding.append((i, arg))
        if binding:
            for i, arg in binding:
                # Import symbols referenced by arg from caller into callee
                self._import_arg_symbols(arg, caller_scope, callee)
                pname = callee.param_symbols()[i].name
                VarReplacer.replace_uses(callee, Temp(name=pname), arg)
                # Propagate bound arguments to sibling scopes that imported
                # this parameter as a free variable (e.g. lambda closures).
                if callee.is_ctor() and callee.parent:
                    orig_name = param_names[i]
                    for sibling in callee.parent.children:
                        if sibling is callee:
                            continue
                        sib_sym = sibling.find_sym(orig_name)
                        if sib_sym and sib_sym.is_free() and sib_sym.is_imported():
                            self._import_arg_symbols(arg, caller_scope, sibling)
                            VarReplacer.replace_uses(sibling, Temp(name=orig_name), arg)
            callee.remove_param([i for i, _ in binding])
            bound_indices = {i for i, _ in binding}
            args = tuple(a for j, a in enumerate(args) if j not in bound_indices)
            ConstantOpt().process(callee)
            if callee.is_ctor():
                # Exclude function-typed bindings from _bound_args — lambda/function
                # arguments are inlined at compile time and not needed for model selection.
                non_func_binding = [(i, exp) for i, exp in binding
                                    if not (i < len(param_syms) and param_syms[i].typ.is_function())]
                callee.parent.set_bound_args(non_func_binding)
        if callee.parent.is_module():
            callee.parent.build_module_params(module_param_vars)
        return args

