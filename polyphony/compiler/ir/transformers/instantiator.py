from .varreplacer import VarReplacer
from ..builtin import builtin_symbols
from ..scope import Scope
from ..ir import *
from ..irhelper import qualified_symbols
from ..irvisitor import IRVisitor
from ..scope import function2method
from ..types.type import Type
from ..analysis.usedef import UseDefDetector
from ..transformers.constopt import ConstantOpt
from ...common.env import env
from ...common import utils
import logging
logger = logging.getLogger()


def find_called_module(scopes) -> list[tuple[Scope, Scope, MOVE]]:
    called_modules: list[tuple[Scope, Scope, MOVE]] = []
    calls: list[tuple[Scope, IRStm, IRCallable]] = []
    for s in scopes:
        calls.extend(CallCollector().process(s))
    for caller_scope, stm, call in calls:
        callee_scope = call.get_callee_scope(caller_scope)
        if isinstance(stm, MOVE) and isinstance(call, NEW) and callee_scope.is_module():
            called_modules.append((callee_scope, caller_scope, cast(MOVE, stm)))
    return called_modules


class ModuleInstantiator(object):
    def process_modules(self, modules: list[tuple[Scope, Scope, MOVE]], names: list[str]):
        new_modules = []
        for (module, caller, move), name in zip(modules, names):
            if not name:
                name = f'{module.instance_number()}'
            new_module = module.instantiate(name, parent=module.parent)
            # If the module is imported from another namespace,
            # the symbol must be registered at the import destination.
            new = cast(NEW, move.src)
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
            assert(isinstance(move.src, NEW))
            new.replace(module.base_name, new_module.base_name)
        return new_modules

    def _process_workers(self, module):
        collector = CallCollector()
        ctor = module.find_ctor()
        calls = collector.process(ctor)
        origin_workers = set()
        for scope, stm, call in calls:
            callee_scope = call.get_callee_scope(scope)
            if isinstance(call, CALL) and callee_scope.base_name == 'append_worker':
                new_worker = self._instantiate_worker(call, ctor, module, scope, origin_workers)
                module.register_worker(new_worker)
        # Remove origin workers
        for worker in origin_workers:
            Scope.destroy(worker)

    def _instantiate_worker(self, call, ctor, module, scope, origin_workers):
        assert len(call.args) >= 1
        _, w = call.args[0]
        assert isinstance(w, IRVariable)
        w_sym = qualified_symbols(w, scope)[-1]
        assert isinstance(w_sym, Symbol)
        assert w_sym.typ.is_function()
        assert w_sym.typ.scope.is_worker()
        worker = w_sym.typ.scope
        origin_workers.add(worker)
        loop = False
        for i, (name, arg) in enumerate(call.args):
            if name == 'loop':
                assert isinstance(arg, CONST) and isinstance(arg.value, bool)
                loop = arg.value
                call.args.pop(i)
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
            call.replace(worker.base_name, new_worker.base_name)
        else:
            call.replace(w, ATTR(TEMP('self'), new_worker.base_name))
        new_worker.add_tag('instantiated')
        return new_worker


class ArgumentApplier(object):
    def process_all(self):
        scopes : list[Scope] = []
        top = Scope.global_scope()
        scopes = [top] + [s for s in top.children if s.is_testbench() and len(s.param_names()) == 0]
        while scopes:
            scopes = self.process_scopes(scopes)

    def process_scopes(self, scopes):
        calls: list[tuple[Scope, IRStm, IRCallable]] = []
        next_scopes = []
        for s in scopes:
            calls.extend(CallCollector().process(s))
        for scope, stm, call in calls:
            callee_scope = call.get_callee_scope(scope)
            if isinstance(call, NEW) and callee_scope.is_module() and callee_scope.is_instantiated():
                ctor = callee_scope.find_ctor()
                assert ctor
                self._bind_args(scope, call.args, ctor)
                next_scopes.append(ctor)
            elif isinstance(call, CALL) and callee_scope.base_name == 'append_worker':
                assert len(call.args) >= 1
                _, w = call.args[0]
                assert isinstance(w, IRVariable)
                w_sym = qualified_symbols(w, scope)[-1]
                assert isinstance(w_sym, Symbol)
                assert w_sym.typ.is_function()
                assert w_sym.typ.scope.is_worker()
                worker = w_sym.typ.scope
                args = call.args[1:]
                self._bind_args(scope, args, worker)
                call.args[1:] = args
        return next_scopes

    def _resolve_seq_arg(self, arg: IRExp, caller_scope: Scope) -> IRExp:
        """Resolve a seq-typed arg to its ARRAY when it was converted to an integer ID.

        objtransform._transform_seq_ctor converts seq definitions to integer symbol IDs
        and stores them as CONST. We recover the original ARRAY either from env.seq_id_to_array
        (for CONST(seq_id) from testbench) or from the caller's usedef (for TEMP vars).
        """
        if isinstance(arg, CONST) and isinstance(arg.value, int):
            array = env.seq_id_to_array.get(arg.value)
            if array is not None:
                return array.clone()
        elif isinstance(arg, IRVariable):
            usedef = UseDefDetector().process(caller_scope)
            qsym = qualified_symbols(arg, caller_scope)
            defs = list(usedef.get_stms_defining(qsym))
            if len(defs) == 1 and isinstance(defs[0], MOVE) and isinstance(defs[0].src, ARRAY):
                return defs[0].src.clone()
        return arg

    def _bind_args(self, caller_scope: Scope, args: list[tuple[str, IRExp]], callee: Scope):
        binding: list[tuple[int, IRExp]] = []
        module_param_vars: list[tuple[str, IRExp]] = []
        param_names = callee.param_names()
        param_syms = callee.param_symbols()
        for i, (_, arg) in enumerate(args):
            if isinstance(arg, IRExp):
                if param_names[i].isupper():
                    module_param_vars.append((param_names[i], arg))
                else:
                    # Resolve seq-typed args (tuple/list) that were converted to integer IDs
                    if i < len(param_syms) and param_syms[i].typ.is_seq():
                        arg = self._resolve_seq_arg(arg, caller_scope)
                    binding.append((i, arg))
        if binding:
            for i, arg in binding:
                pname = callee.param_symbols()[i].name
                VarReplacer.replace_uses(callee, TEMP(pname), arg)
            callee.remove_param([i for i, _ in binding])
            for i, _ in reversed(binding):
                args.pop(i)
            ConstantOpt().process(callee)
            if callee.is_ctor():
                callee.parent.set_bound_args(binding)
        if callee.parent.is_module():
            callee.parent.build_module_params(module_param_vars)


class CallCollector(IRVisitor):
    def __init__(self):
        super().__init__()
        self.calls: list[tuple[Scope, IRStm, IRCallable]] = []

    def process(self, scope: Scope):
        super().process(scope)
        return self.calls

    def visit_CALL(self, ir):
        self.calls.append((self.scope, self.current_stm, ir))

    def visit_NEW(self, ir):
        self.calls.append((self.scope, self.current_stm, ir))

    def visit_SYSCALL(self, ir):
        if ir.name == '$new':
            self.calls.append((self.scope, self.current_stm, ir))
