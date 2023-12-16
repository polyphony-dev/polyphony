import inspect
from .varreplacer import VarReplacer
from ..builtin import builtin_symbols
from ..scope import Scope
from ..ir import *
from ..irhelper import qualified_symbols
from ..irvisitor import IRVisitor
from ..types.type import Type
from ..analysis.usedef import UseDefDetector
from ...common.env import env
from ...common import utils
import logging
logger = logging.getLogger()


def bind_val(scope: Scope, i: int, exp: IRExp):
    VarReplacer.replace_uses(scope, TEMP(scope.param_symbols()[i].name), exp)


class ModuleInstantiator(object):
    def process_scopes(self, scopes):
        new_modules = self._process_called_module(scopes)
        return new_modules

    def _process_module(self):
        scopes = Scope.get_scopes(bottom_up=False,
                                  with_global=False,
                                  with_class=True,
                                  with_lib=False)
        modules = [s for s in scopes if s.is_module()]

        new_modules = set()
        for target, args in env.targets:
            if not target.is_module():
                target.add_tag('instantiated')
                new_modules.add(target)
                continue
            new_module = self._instantiate_module(module, args)
            self._process_workers(new_module)
            new_modules.add(new_module)
        return new_modules

    def _process_called_module(self, scopes):
        calls: list[tuple[Scope, IRStm, IRCallable]] = []
        for s in scopes:
            calls.extend(CallCollector().process(s))
        new_modules = self._process_called_module_sub(calls)
        return new_modules

    def _process_called_module_sub(self, calls: list[tuple[Scope, IRStm, IRCallable]]):
        new_modules = set()
        for scope, stm, call in calls:
            callee_scope = call.get_callee_scope(scope)
            if call.is_a(NEW) and callee_scope.is_module() and not callee_scope.is_instantiated():
                new_module = self._instantiate_called_module(scope, call, stm.dst)
                self._process_workers(new_module)
                self._process_objects(new_module)
                new_modules.add(new_module)
                dst_sym = qualified_symbols(stm.dst, scope)[-1]
                assert isinstance(dst_sym, Symbol)
                dst_sym.typ = Type.object(new_module)
        return new_modules

    def _instantiate_called_module(self, scope: Scope, new: NEW, module_var: IRVariable):
        module = new.get_callee_scope(scope)
        binding: list[tuple[int, IRExp]] = []
        module_param_vars: list[tuple[str, IRExp]] = []
        ctor = module.find_ctor()
        assert ctor
        param_names = ctor.param_names()
        for i, (_, arg) in enumerate(new.args):
            if isinstance(arg, IRExp):
                if param_names[i].isupper():
                    module_param_vars.append((param_names[i], arg))
                else:
                    binding.append((i, arg))

        module_var_sym = qualified_symbols(module_var, scope)[-1]
        assert isinstance(module_var_sym, Symbol)
        inst_name = module_var_sym.hdl_name()
        ctor = module.find_ctor()
        # children = [ctor]
        # children.extend([c for c in module.collect_scope() if c.is_assigned()])
        # collect children scopes from the module without workers
        children = []
        children.extend([c for c in module.collect_scope() if not c.is_worker()])
        if scope.is_global():
            parent = None
        else:
            parent = scope.parent
        new_module = module.instantiate(inst_name, children, parent=parent)
        if binding:
            new_module_ctor = new_module.find_ctor()
            assert new_module_ctor
            udd = UseDefDetector()
            udd.process(new_module_ctor)
            for i, a in binding:
                bind_val(new_module_ctor, i, a)
            new_module_ctor.remove_param([i for i, _ in binding])
            new_sym = qualified_symbols(new, scope)[-1]
            assert isinstance(new_sym, Symbol)
            new_module_sym = new_sym.scope.inherit_sym(new_sym, new_module.base_name)
            for i, _ in reversed(binding):
                new.args.pop(i)
        else:
            new_sym = qualified_symbols(new, scope)[-1]
            assert isinstance(new_sym, Symbol)
            new_module_sym = new_sym.scope.inherit_sym(new_sym, new_module.base_name)
        func = new.func.clone()
        func.name = new_module_sym.name
        new.func = func
        new_module.inst_name = inst_name
        new_module.build_module_params(module_param_vars)
        return new_module

    def _instantiate_module(self, module, args):
        binding: list[tuple[int, IRExp]] = []
        module_param_vars: list[tuple[str, IRExp]] = []
        ctor = module.find_ctor()
        for i, arg in enumerate(args):
            if isinstance(arg, (int, str)):
                if ctor.params[i + 1].copy.name.isupper():
                    module_param_vars.append((ctor.params[i + 1].copy.name, arg))
                else:
                    binding.append((i, arg))
        inst_name = 'x'
        ctor = module.find_ctor()
        children = [ctor]
        children.extend([c for c in module.collect_scope() if c.is_assigned()])
        if binding:
            new_module = module.instantiate(inst_name, children)
            new_module_ctor = new_module.find_ctor()
            udd = UseDefDetector()
            udd.process(new_module_ctor)
            for i, a in binding:
                bind_val(new_module_ctor, i, a)
            new_module_ctor.remove_param([i for i, _ in binding])
        else:
            new_module = module.instantiate(inst_name, children)
        new_module.inst_name = inst_name
        new_module.build_module_params(module_param_vars)
        return new_module

    def _process_workers(self, module):
        collector = CallCollector()
        ctor = module.find_ctor()
        calls = collector.process(ctor)
        for scope, stm, call in calls:
            callee_scope = call.get_callee_scope(scope)
            if call.is_a(CALL) and callee_scope.base_name == 'append_worker':
                new_worker, is_created = self._instantiate_worker(call, ctor, module, scope)
                module.register_worker(new_worker)
                if not is_created:
                    continue
                new_worker_sym = module.add_sym(new_worker.base_name,
                                                #tags={'worker'},
                                                tags=set(),
                                                typ=Type.function(new_worker))
                _, w = call.args[0]
                w.symbol = new_worker_sym

    def _instantiate_worker(self, call, ctor, module, scope):
        assert len(call.args) >= 1
        _, w = call.args[0]
        assert w.is_a(IRVariable)
        w_sym = qualified_symbols(w, scope)[-1]
        assert isinstance(w_sym, Symbol)
        assert w_sym.typ.is_function()
        assert w_sym.typ.scope.is_worker()
        worker = w_sym.typ.scope
        binding = []
        loop = False
        for i, (name, arg) in enumerate(call.args):
            if i == 0:
                continue
            if name == 'loop':
                assert arg.is_a(CONST) and isinstance(arg.value, bool)
                loop = arg.value
                continue
            if isinstance(arg, IRExp):
                # adjust the index for the first parameter of append_worker()
                binding.append((i - 1, arg))
            else:
                pass

        idstr = str(worker.instance_number())
        if worker.is_instantiated():
            new_worker = worker
        else:
            if binding:
                postfix = '{}_{}'.format(idstr, '_'.join([str(v) for _, v in binding]))
            else:
                postfix = idstr
            new_worker = worker.clone('', postfix, module)

        if loop:
            new_worker.add_tag('loop_worker')
        if binding:
            udd = UseDefDetector()
            udd.process(new_worker)
            for i, a in binding:
                bind_val(new_worker, i, a)
            new_worker.remove_param([i for i, _ in binding])
            for i, _ in reversed(binding):
                # adjust the index for the first parameter of append_worker()
                call.args.pop(i + 1)
        # Replace old worker references with new worker references
        call.replace(worker.base_name, new_worker.base_name)

        # Replace old module references with new module references
        module_syms = worker.find_scope_sym(module.origin)
        for sym in module_syms:
            new_sym = new_worker.cloned_symbols[sym]
            new_sym.typ = new_sym.typ.clone(scope=module)

        if worker.is_instantiated():
            return new_worker, False
        else:
            children = [c for c in worker.collect_scope() if c.is_closure()]
            scope_map = {worker:new_worker}
            for child in children:
                new_child = worker._clone_child(new_worker, worker, child)
                new_child.add_tag('instantiated')
                scope_map[child] = new_child
            for old, new in scope_map.items():
                syms = new_worker.find_scope_sym(old)
                for sym in syms:
                    if sym.scope in scope_map.values():
                        sym.typ = sym.typ.clone(scope=new)
            new_worker.add_tag('instantiated')
            return new_worker, True

    def _process_objects(self, module):
        collector = CallCollector()
        ctor = module.find_ctor()
        calls = collector.process(ctor)
        for scope, stm, call in calls:
            if call.is_a(SYSCALL) and call.name == '$new':
                # TODO
                pass


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
