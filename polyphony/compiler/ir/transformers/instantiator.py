import inspect
from .varreplacer import VarReplacer
from ..builtin import builtin_symbols
from ..scope import Scope
from ..ir import *
from ..irhelper import qualified_symbols
from ..irvisitor import IRVisitor
from ..types.type import Type
from ..analysis.usedef import UseDefDetector
from ..transformers.constopt import ConstantOpt
from ...common.env import env
from ...common import utils
import logging
logger = logging.getLogger()


def find_called_module(scopes) -> list[tuple[Scope, MOVE]]:
    called_modules: list[tuple[Scope, MOVE]] = []
    calls: list[tuple[Scope, IRStm, IRCallable]] = []
    for s in scopes:
        calls.extend(CallCollector().process(s))
    for scope, stm, call in calls:
        callee_scope = call.get_callee_scope(scope)
        if stm.is_a(MOVE) and call.is_a(NEW) and callee_scope.is_module():
            called_modules.append((callee_scope, cast(MOVE, stm)))
    return called_modules


class ModuleInstantiator(object):
    def process_modules(self, modules: list[tuple[Scope, MOVE]], names: list[str]):
        new_modules = []
        for (module, move), name in zip(modules, names):
            if not name:
                name = f'{module.instance_number()}'
            new_module = module.instantiate(name, parent=module.parent)
            self._process_workers(new_module)
            new_module.add_tag('instantiated')
            for s in new_module.collect_scope():
                s.add_tag('instantiated')
            new_modules.append(new_module)
            assert(isinstance(move.src, NEW))
            new = move.src
            new.replace(module.base_name, new_module.base_name)
        return new_modules

    def _process_workers(self, module):
        collector = CallCollector()
        ctor = module.find_ctor()
        calls = collector.process(ctor)
        origin_workers = set()
        for scope, stm, call in calls:
            callee_scope = call.get_callee_scope(scope)
            if call.is_a(CALL) and callee_scope.base_name == 'append_worker':
                new_worker = self._instantiate_worker(call, ctor, module, scope, origin_workers)
                module.register_worker(new_worker)
        # Remove origin workers
        for worker in origin_workers:
            Scope.destroy(worker)

    def _instantiate_worker(self, call, ctor, module, scope, origin_workers):
        assert len(call.args) >= 1
        _, w = call.args[0]
        assert w.is_a(IRVariable)
        w_sym = qualified_symbols(w, scope)[-1]
        assert isinstance(w_sym, Symbol)
        assert w_sym.typ.is_function()
        assert w_sym.typ.scope.is_worker()
        worker = w_sym.typ.scope
        origin_workers.add(worker)
        loop = False
        for i, (name, arg) in enumerate(call.args):
            if name == 'loop':
                assert arg.is_a(CONST) and isinstance(arg.value, bool)
                loop = arg.value
                call.args.pop(i)
                break

        if worker.is_instantiated():
            new_worker = worker
        else:
            new_worker = worker.clone('', f'{worker.instance_number()}', module, recursive=True)

        if loop:
            new_worker.add_tag('loop_worker')
        # Replace old worker references with new worker references
        call.replace(worker.base_name, new_worker.base_name)
        new_worker.add_tag('instantiated')
        return new_worker


class ArgumentApplier(object):
    def process_all(self):
        scopes : list[Scope] = []
        scopes.append(Scope.global_scope())
        while scopes:
            scopes = self.process_scopes(scopes)

    def process_scopes(self, scopes):
        calls: list[tuple[Scope, IRStm, IRCallable]] = []
        next_scopes = []
        for s in scopes:
            calls.extend(CallCollector().process(s))
        for scope, stm, call in calls:
            callee_scope = call.get_callee_scope(scope)
            if call.is_a(NEW) and callee_scope.is_module() and callee_scope.is_instantiated():
                ctor = callee_scope.find_ctor()
                assert ctor
                self._bind_args(scope, call.args, ctor)
                next_scopes.append(ctor)
            elif call.is_a(CALL) and callee_scope.base_name == 'append_worker':
                assert len(call.args) >= 1
                _, w = call.args[0]
                assert w.is_a(IRVariable)
                w_sym = qualified_symbols(w, scope)[-1]
                assert isinstance(w_sym, Symbol)
                assert w_sym.typ.is_function()
                assert w_sym.typ.scope.is_worker()
                worker = w_sym.typ.scope
                args = call.args[1:]
                self._bind_args(scope, args, worker)
                call.args[1:] = args
        return next_scopes

    def _bind_args(self, caller_scope: Scope, args: list[tuple[str, IRExp]], callee: Scope):
        binding: list[tuple[int, IRExp]] = []
        module_param_vars: list[tuple[str, IRExp]] = []
        param_names = callee.param_names()
        for i, (_, arg) in enumerate(args):
            if isinstance(arg, IRExp):
                if param_names[i].isupper():
                    module_param_vars.append((param_names[i], arg))
                else:
                    binding.append((i, arg))
        if binding:
            UseDefDetector().process(callee)
            for i, arg in binding:
                VarReplacer.replace_uses(callee, TEMP(callee.param_symbols()[i].name), arg)
            callee.remove_param([i for i, _ in binding])
            for i, _ in reversed(binding):
                args.pop(i)
            UseDefDetector().process(callee)
            ConstantOpt().process(callee)
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
