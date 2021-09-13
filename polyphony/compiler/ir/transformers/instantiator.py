import inspect
from .varreplacer import VarReplacer
from ..scope import Scope
from ..ir import *
from ..irvisitor import IRVisitor
from ..type import Type
from ..analysis.usedef import UseDefDetector
from ...common.env import env
from ...common import utils
import logging
logger = logging.getLogger()


def bind_val(scope, i, value):
    VarReplacer.replace_uses(scope, TEMP(scope.params[i][0], Ctx.LOAD), CONST(value))


class EarlyWorkerInstantiator(object):
    def process_all(self):
        assert env.config.enable_pure
        new_workers = set()
        orig_workers = set()
        for name, inst in env.runtime_info.module_instances.items():
            new_worker, orig_worker = self._process_workers(name, inst)
            if new_worker:
                new_workers = new_workers | new_worker
                orig_workers = orig_workers | orig_worker
        return new_workers, orig_workers

    def _process_workers(self, name, instance):
        modules = [scope for scope in env.scopes.values() if scope.is_module()]
        module = None
        for m in modules:
            if hasattr(m, 'inst_name') and m.inst_name == name:
                module = m
                break
        if not module:
            return None, None

        new_workers = set()
        orig_workers = set()
        for worker in instance._workers:
            new_worker, orig_worker = self._instantiate_worker(worker, name, module)
            new_workers.add(new_worker)
            module.register_worker(new_worker, [])
            orig_workers.add(orig_worker)
            if orig_worker in module.children:
                module.children.remove(orig_worker)
        return new_workers, orig_workers

    def _instantiate_worker(self, worker, inst_name, module):
        if inspect.isfunction(worker.func):
            worker_scope_name = '{}.{}'.format(env.global_scope_name, worker.func.__qualname__)
            worker_scope = env.scopes[worker_scope_name]
            parent = worker_scope.parent
        elif inspect.ismethod(worker.func):
            worker_scope_name = '{}.{}'.format(env.global_scope_name, worker.func.__qualname__)
            worker_scope = env.scopes[worker_scope_name]
            parent = module
        _, lineno = inspect.getsourcelines(worker.func)
        if not worker_scope.is_worker():
            worker_scope.add_tag('worker')

        binding = []
        for i, arg in enumerate(worker.args):
            if isinstance(arg, (int, bool, str)):
                if worker_scope.is_method():
                    binding.append((bind_val, i + 1, arg))  # skip 'self'
                else:
                    binding.append((bind_val, i, arg))
            else:
                pass
        idstr = str(worker.instance_number())
        if binding:
            # FIXME: use scope-id instead of lineno
            postfix = '{}_{}'.format(idstr,
                                     '_'.join([str(v) for _, _, v in binding]))
            new_worker = worker_scope.clone('', postfix, parent=parent)

            udd = UseDefDetector()
            udd.process(new_worker)
            for f, i, a in binding:
                f(new_worker, i, a)
            for _, i, _ in reversed(binding):
                new_worker.params.pop(i)
        else:
            new_worker = worker_scope.clone('', idstr, parent=parent)
        new_worker.add_tag('instantiated')
        if inspect.ismethod(worker.func):
            self_sym = new_worker.find_sym(env.self_name)
            self_sym.typ = self_sym.typ.with_scope(module)
        parent.add_sym(new_worker.base_name, typ=Type.function(new_worker))
        env.runtime_info.inst2worker[worker] = (new_worker, worker_scope)
        return new_worker, worker_scope


class EarlyModuleInstantiator(object):
    def process_all(self):
        assert env.config.enable_pure
        new_modules = set()
        for name, inst in env.runtime_info.module_instances.items():
            new_module, orig_module = self._instantiate_module(name, inst)
            if new_module:
                env.runtime_info.inst2module[new_module.instance] = (new_module, orig_module)
                new_modules.add(new_module)
        return new_modules

    def _instantiate_module(self, inst_name, instance):
        scope_name = '{}.{}'.format(env.global_scope_name, instance.__class__.__qualname__)
        if scope_name not in env.scopes:
            scope_name = '{}.{}'.format(instance.__module__, instance.__class__.__qualname__)
        assert scope_name in env.scopes
        module = env.scopes[scope_name]
        module.inst_name = ''
        ctor = module.find_ctor()
        if not ctor.is_pure():
            return None, None

        new_module_name = module.base_name + '_' + inst_name

        overrides = [child for child in module.children if not child.is_lib() and not child.is_worker()]
        for method in overrides[:]:
            for worker in instance._workers:
                if method.base_name == worker.func.__name__:
                    if method in overrides:
                        overrides.remove(method)
        new_module = module.inherit(new_module_name, overrides)
        new_module.inst_name = inst_name
        new_module.instance = instance
        new_module.add_tag('instantiated')
        self._replace_module_call(inst_name, module, new_module)
        return new_module, module

    def _replace_module_call(self, inst_name, module, new_module):
        caller_lineno = -1
        caller_scope = None
        inst = env.runtime_info.module_instances[inst_name]
        for node in env.runtime_info.ctor_nodes:
            if node.obj is inst:
                caller_lineno = node.caller_lineno
                preds = env.runtime_info.call_graph.preds(node)
                assert len(preds) == 1
                pred_node = list(preds)[0]
                if pred_node.obj is None:
                    caller_scope = Scope.global_scope()
                else:
                    typ = Type.from_expr(pred_node.obj, Scope.global_scope())
                    assert typ.is_object()
                    caller_scope = typ.get_scope().find_ctor()
                break
        collector = CallCollector()
        calls = collector.process(caller_scope)
        for stm, call in calls:
            if call.is_a(NEW) and call.func_scope() is module and caller_lineno == stm.loc.lineno:
                obj_name = inst_name.split('.')[-1]
                if stm.dst.symbol().name.endswith(obj_name):
                    new_module_sym = call.sym.scope.gen_sym(new_module.base_name)
                    new_module_sym.typ = Type.klass(new_module)
                    call.sym = new_module_sym


class WorkerInstantiator(object):
    def process_all(self):
        self.new_scopes = set()
        self._process_global_module()
        return self.new_scopes

    def _process_global_module(self):
        collector = CallCollector()
        calls = []
        scopes = Scope.get_scopes(bottom_up=False,
                                  with_global=True,
                                  with_class=False,
                                  with_lib=False)
        for s in scopes:
            if s.is_global() or s.is_function_module():
                calls.extend(collector.process(s))
        for stm, call in calls:
            if call.is_a(NEW) and call.func_scope().is_module() and not call.func_scope().find_ctor().is_pure():
                self._process_workers(call.func_scope())

    def _process_workers(self, module):
        collector = CallCollector()
        ctor = module.find_ctor()
        calls = collector.process(ctor)
        for stm, call in calls:
            if call.is_a(CALL) and call.func_scope().base_name == 'append_worker':
                new_worker, is_created = self._instantiate_worker(call, ctor, module)
                module.register_worker(new_worker, call.args)
                if not is_created:
                    continue
                new_worker_sym = module.add_sym(new_worker.base_name,
                                                typ=Type.function(new_worker))
                _, w = call.args[0]
                w.set_symbol(new_worker_sym)
        #return new_workers

    def _instantiate_worker(self, call, ctor, module):
        assert len(call.args) >= 1
        _, w = call.args[0]
        assert w.is_a([TEMP, ATTR])
        assert w.symbol().typ.is_function()
        assert w.symbol().typ.get_scope().is_worker()
        worker = w.symbol().typ.get_scope()
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
                binding.append((bind_val, i, arg.value))
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
            for f, i, a in binding:
                f(new_worker, i, a)
            for _, i, _ in reversed(binding):
                new_worker.params.pop(i)
            for _, i, _ in reversed(binding):
                if worker.is_function():
                    # adjust the index for the first parameter of append_worker()
                    call.args.pop(i + 1)
                else:
                    call.args.pop(i)
        # Replace old module references with new module references
        module_syms = worker.find_scope_sym(module.origin)
        for sym in module_syms:
            new_sym = new_worker.cloned_symbols[sym]
            new_sym.typ = new_sym.typ.with_scope(module)

        if worker.is_instantiated():
            return new_worker, False
        else:
            self.new_scopes.add(new_worker)
            children = [c for c in worker.collect_scope() if c.is_closure()]
            scope_map = {worker:new_worker}
            for child in children:
                new_child = worker._clone_child(new_worker, worker, child)
                new_child.add_tag('instantiated')
                scope_map[child] = new_child
                self.new_scopes.add(new_child)
            for old, new in scope_map.items():
                syms = new_worker.find_scope_sym(old)
                for sym in syms:
                    if sym.scope in scope_map.values():
                        sym.typ = sym.typ.with_scope(new)
            new_worker.add_tag('instantiated')
            return new_worker, True

class ModuleInstantiator(object):
    def process_all(self):
        new_modules = self._process_global_module()
        return new_modules

    def _process_global_module(self):
        collector = CallCollector()
        new_modules = set()
        calls = []
        scopes = Scope.get_scopes(bottom_up=False,
                                  with_global=True,
                                  with_class=False,
                                  with_lib=False)
        for s in scopes:
            if s.is_global() or s.is_function_module():
                calls.extend(collector.process(s))
        for stm, call in calls:
            if call.is_a(NEW) and call.func_scope().is_module() and not call.func_scope().is_instantiated():
                new_module = self._instantiate_module(call, stm.dst)
                new_modules.add(new_module)
                stm.dst.symbol().typ = Type.object(new_module)
        return new_modules

    def _instantiate_module(self, new, module_var):
        module = new.func_scope()
        binding = []
        module_param_vars = []
        ctor = module.find_ctor()
        for i, (_, arg) in enumerate(new.args):
            if arg.is_a(CONST):
                if ctor.params[i + 1].copy.name.isupper():
                    module_param_vars.append((ctor.params[i + 1].copy.name, arg.value))
                else:
                    binding.append((bind_val, i, arg.value))
        inst_name = module_var.symbol().hdl_name()
        ctor = module.find_ctor()
        children = [ctor]
        children.extend([c for c in module.collect_scope() if c.is_assigned()])
        if binding:
            new_module = module.instantiate(inst_name, children)
            new_module_ctor = new_module.find_ctor()
            udd = UseDefDetector()
            udd.process(new_module_ctor)
            for f, i, a in binding:
                f(new_module_ctor, i + 1, a)
            for _, i, _ in reversed(binding):
                new_module_ctor.params.pop(i + 1)
            new_module_sym = new.sym.scope.inherit_sym(new.sym, new_module.name)
            new.sym = new_module_sym
            for _, i, _ in reversed(binding):
                new.args.pop(i)
        else:
            new_module = module.instantiate(inst_name, children)
            new_module_sym = new.sym.scope.inherit_sym(new.sym, new_module.name)
            new.sym = new_module_sym
        new.sym.typ = new.sym.typ.with_scope(new_module)
        new_module.inst_name = inst_name
        new_module.module_params = []
        ctor = new_module.find_ctor()
        for i, param in enumerate(ctor.params):
            if param.copy.name.isupper():
                new_module.module_params.append(param)
        new_module.module_param_vars = module_param_vars
        for param in new_module.module_params:
            ctor.params.remove(param)
        return new_module


class CallCollector(IRVisitor):
    def __init__(self):
        super().__init__()
        self.calls = []

    def process(self, scope):
        super().process(scope)
        return self.calls

    def visit_CALL(self, ir):
        self.calls.append((self.current_stm, ir))

    def visit_NEW(self, ir):
        self.calls.append((self.current_stm, ir))
