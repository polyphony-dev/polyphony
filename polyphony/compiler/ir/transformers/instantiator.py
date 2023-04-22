import inspect
from .varreplacer import VarReplacer
from ..scope import Scope
from ..ir import *
from ..irvisitor import IRVisitor
from ..types.type import Type
from ..analysis.usedef import UseDefDetector
from ...common.env import env
from ...common import utils
import logging
logger = logging.getLogger()


def bind_val(scope, i, value):
    VarReplacer.replace_uses(scope, TEMP(scope.param_symbols()[i], Ctx.LOAD), CONST(value))


class ModuleInstantiator(object):
    def process_all(self):
        new_modules = self._process_called_module()
        # new_modules = self._process_module()  # instantiate for env.targets
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
            #stm.dst.symbol.typ = Type.object(new_module)
        return new_modules

    def _process_called_module(self):
        scopes = Scope.get_scopes(bottom_up=False,
                                  with_global=True,
                                  with_class=False,
                                  with_lib=False)
        calls = []
        for s in scopes:
            if s.is_global() or s.is_function_module():
                calls.extend(CallCollector().process(s))
        new_modules = set()
        for scope, stm, call in calls:
            callee_scope = call.callee_scope
            if call.is_a(NEW) and callee_scope.is_module() and not callee_scope.is_instantiated():
                new_module = self._instantiate_called_module(scope, call, stm.dst)
                self._process_workers(new_module)
                self._process_objects(new_module)
                new_modules.add(new_module)
                stm.dst.symbol.typ = Type.object(new_module)
        return new_modules

    def _process_inner_scope(self, ctor):
        calls = CallCollector().process(ctor)
        new_scopes = set()
        for scope, stm, call in calls:
            new_scope = self._instantiate(call, stm.dst)
            new_scopes.add(new_scope)
            stm.dst.symbol.typ = Type.object(new_scope)
        return new_scopes

    def _instantiate_called_module(self, scope, new, module_var):
        module = new.callee_scope
        binding = []
        module_param_vars = []
        ctor = module.find_ctor()
        param_names = ctor.param_names()
        for i, (_, arg) in enumerate(new.args):
            if arg.is_a(CONST):
                if param_names[i].isupper():
                    module_param_vars.append((param_names[i], arg.value))
                else:
                    binding.append((i, arg.value))
        inst_name = module_var.symbol.hdl_name()
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
            new_module_sym = new.symbol.scope.inherit_sym(new.symbol, new_module.name)
            new.symbol = new_module_sym
            for i, _ in reversed(binding):
                new.args.pop(i)
        else:
            new_module = module.instantiate(inst_name, children)
            new_module_sym = new.symbol.scope.inherit_sym(new.symbol, new_module.name)
            new.symbol = new_module_sym
        new.symbol.typ = new.symbol.typ.clone(scope=new_module)
        new_module.inst_name = inst_name
        new_module.build_module_params(module_param_vars)
        return new_module

    def _instantiate_module(self, module, args):
        binding = []
        module_param_vars = []
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
            #new_module_sym = new.sym.scope.inherit_sym(new.sym, new_module.name)
            #new.sym = new_module_sym
            #for i, _ in reversed(binding):
            #    new.args.pop(i)
        else:
            new_module = module.instantiate(inst_name, children)
            #new_module_sym = new.sym.scope.inherit_sym(new.sym, new_module.name)
            #new.sym = new_module_sym
        #new.sym.typ = new.sym.typ.clone(scope=new_module)
        new_module.inst_name = inst_name
        new_module.build_module_params(module_param_vars)
        return new_module

    def _process_workers(self, module):
        collector = CallCollector()
        ctor = module.find_ctor()
        calls = collector.process(ctor)
        for scope, stm, call in calls:
            callee_scope = call.callee_scope
            if call.is_a(CALL) and callee_scope.base_name == 'append_worker':
                new_worker, is_created = self._instantiate_worker(call, ctor, module)
                module.register_worker(new_worker, call.args)
                if not is_created:
                    continue
                new_worker_sym = module.add_sym(new_worker.base_name,
                                                typ=Type.function(new_worker))
                _, w = call.args[0]
                w.symbol = new_worker_sym
        #return new_workers

    def _instantiate_worker(self, call, ctor, module):
        assert len(call.args) >= 1
        _, w = call.args[0]
        assert w.is_a([TEMP, ATTR])
        assert w.symbol.typ.is_function()
        assert w.symbol.typ.scope.is_worker()
        worker = w.symbol.typ.scope
        binding = []
        loop = False
        for i, (name, arg) in enumerate(call.args):
            if i == 0:
                continue
            if name == 'loop':
                assert arg.is_a(CONST)
                loop = arg.value
                continue
            if arg.is_a(CONST):
                if worker.is_function():
                    # adjust the index for the first parameter of append_worker()
                    i -= 1
                binding.append((i, arg.value))
            else:
                pass

        idstr = str(worker.instance_number())
        if worker.is_instantiated():
            new_worker = worker
        else:
            if binding:
                postfix = '{}_{}'.format(idstr, '_'.join([str(v) for _, _, v in binding]))
            else:
                postfix = idstr
            new_worker = worker.clone(module.inst_name, postfix, module)

        if loop:
            new_worker.add_tag('loop_worker')
        if binding:
            udd = UseDefDetector()
            udd.process(new_worker)
            for i, a in binding:
                bind_val(new_worker, i, a)
            new_worker.remove_params([i for i, _ in binding])
            for i, _ in reversed(binding):
                if worker.is_function():
                    # adjust the index for the first parameter of append_worker()
                    call.args.pop(i + 1)
                else:
                    call.args.pop(i)
        # Replace old module references with new module references
        module_syms = worker.find_scope_sym(module.origin)
        for sym in module_syms:
            new_sym = new_worker.cloned_symbols[sym]
            new_sym.typ = new_sym.typ.clone(scope=module)

        if worker.is_instantiated():
            return new_worker, False
        else:
            #self.new_scopes.add(new_worker)
            children = [c for c in worker.collect_scope() if c.is_closure()]
            scope_map = {worker:new_worker}
            for child in children:
                new_child = worker._clone_child(new_worker, worker, child)
                new_child.add_tag('instantiated')
                scope_map[child] = new_child
                #self.new_scopes.add(new_child)
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
            if call.is_a(SYSCALL) and call.symbol.name == '$new':
                # TODO
                pass


class CallCollector(IRVisitor):
    def __init__(self):
        super().__init__()
        self.calls = []

    def process(self, scope):
        super().process(scope)
        return self.calls

    def visit_CALL(self, ir):
        self.calls.append((self.scope, self.current_stm, ir))

    def visit_NEW(self, ir):
        self.calls.append((self.scope, self.current_stm, ir))

    def visit_SYSCALL(self, ir):
        if ir.symbol.name == '$new':
            self.calls.append((self.scope, self.current_stm, ir))
