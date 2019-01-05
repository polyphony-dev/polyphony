import copy
import inspect
import os
import sys
import threading
import traceback
from collections import namedtuple, defaultdict
from .common import fail, warn
from .constopt import ConstantOptBase
from .errors import Errors, Warnings, InterpretError
from .env import env
from .graph import Graph
from .ir import Ctx, CONST, TEMP, ATTR, ARRAY, CALL, NEW, MOVE, EXPR
from .irhelper import expr2ir
from .scope import Scope
from .setlineno import LineNumberSetter
from .type import Type


def interpret(source, file_name=''):
    stdout = sys.stdout
    sys.stdout = None
    objs = {}
    rtinfo = RuntimeInfo()
    builder = RuntimeInfoBuilder(rtinfo)
    # We have to save the environment to avoid any import side-effect by the interpreter
    saved_sys_path = sys.path
    saved_sys_modules = sys.modules
    sys.path = sys.path.copy()
    sys.modules = sys.modules.copy()
    if file_name:
        dir_name = os.path.dirname(file_name)
        sys.path.append(dir_name)
    threading.setprofile(builder._profile_func)
    thread = threading.Thread(target=_do_interpret, args=(source, file_name, objs))
    thread.start()
    # TODO: busy loop?
    while thread.is_alive():
        thread.join(1)
    threading.setprofile(None)
    sys.stdout = stdout

    if thread.exc_info:
        _, exc, tb = thread.exc_info
        if isinstance(exc, InterpretError):
            raise exc
        else:
            if env.verbose_level:
                traceback.print_tb(tb)
            warn(None, Warnings.EXCEPTION_RAISED)
    builder.build()
    rtinfo.pyfuncs = _make_pyfuncs(objs)
    module_classes = _find_module_classes(rtinfo.ctor_nodes)
    for cls in module_classes:
        pyfuncs = _make_pyfuncs(cls.__dict__)
        rtinfo.pyfuncs.update(pyfuncs)
    instances = _find_module_instances(objs, module_classes)
    rtinfo.module_classes = module_classes
    rtinfo.module_instances = instances
    namespace_names = [scp.name for scp in env.scopes.values() if scp.is_namespace() and not scp.is_global()]
    _vars, _namespaces = _find_vars('__main__', objs, set(), namespace_names)
    _namespaces['__main__'] = _vars['__main__']
    rtinfo.global_vars = _namespaces
    env.runtime_info = rtinfo
    sys.path = saved_sys_path
    sys.modules = saved_sys_modules


def _do_interpret(source, file_name, objs):
    code = compile(source, file_name, 'exec')
    th = threading.current_thread()
    th.exc_info = None
    try:
        objs['__name__'] = '__main__'
        exec(code, objs)
    except Exception:
        th.exc_info = sys.exc_info()


MethodCall = namedtuple('MethodCall', ('name', 'args'))
MethodInternalCall = namedtuple('MethodInternalCall', ('name', 'self', 'args'))


class FrameNode(object):
    def __init__(self, name, vars, order, lineno, caller_lineno):
        self.name = name
        self.vars = vars
        self.order = order
        self.lineno = lineno
        self.caller_lineno = caller_lineno
        self.is_pure = False
        self.is_module_ctor = False
        self.is_pure_internal = False
        self.is_top_module = False
        self.obj = None
        self.call = None
        self.internal_calls = []
        self.ret = None

    def __str__(self):
        return '{} {} {}'.format(self.name, self.is_pure, self.is_module_ctor)

    def __repr__(self):
        return '{}:{}:{}'.format(self.name, self.lineno, self.caller_lineno)


class RuntimeInfo(object):
    def __init__(self):
        self.object_defaults = {}
        self.inst2module = {}
        self.inst2worker = {}
        self.call_graph = None
        self.pure_nodes = []
        self.ctor_nodes = []

    def get_internal_calls(self, instance):
        for node in self.ctor_nodes:
            if node.obj is instance:
                return node.internal_calls
        return None


class RuntimeInfoBuilder(object):
    def __init__(self, rtinfo):
        self.rtinfo = rtinfo
        self.call_stack_info = []
        self.exec_order = 0

    def _profile_func(self, frame, event, arg):
        if event == 'call' or event == 'return':
            self.exec_order += 1
            name = frame.f_code.co_name
            vars = frame.f_locals
            if frame.f_back:
                self.call_stack_info.append((name, vars, self.exec_order, frame.f_lineno, frame.f_back.f_lineno, event, arg))
            else:
                self.call_stack_info.append((name, vars, self.exec_order, frame.f_lineno, 0, event, arg))

    def build(self):
        call_graph = self.build_runtime_call_graph()
        pure_nodes, ctor_nodes = self._simplify_call_graph(call_graph)
        self._set_module_ctor_info(call_graph, ctor_nodes)
        self.rtinfo.call_graph = call_graph
        self.rtinfo.pure_nodes = pure_nodes
        self.rtinfo.ctor_nodes = ctor_nodes

    def build_runtime_call_graph(self):
        call_graph = Graph()
        top = FrameNode('', {}, -1, -1, -1)
        prev = top
        for name, vars, order, lineno, caller_lineno, ev, arg in self.call_stack_info:
            if ev == 'call':
                next = FrameNode(name, vars, order, lineno, caller_lineno)
                call_graph.add_edge(prev, next)
                prev = next
            else:
                prev.ret = arg
                if prev.caller_lineno != -1:
                    prev = list(call_graph.preds(prev))[0]
        return call_graph

    def _simplify_call_graph(self, call_graph):
        ''' extract decorators in the graph '''
        pure_nodes = []
        ctor_nodes = []
        nodes = sorted(call_graph.nodes, key=lambda n: n.order)
        for node in nodes:
            if node.name == '_pure_decorator':
                succs = call_graph.succs(node)
                if not succs:
                    # in this case, we've already replaced the node's connection
                    continue
                succ_node = list(succs)[0]
                succ_node.is_pure = True
                succ_node.caller_lineno = node.caller_lineno
                pure_nodes.append(succ_node)
                preds = call_graph.preds(node)
                assert len(preds) == 1
                pred_node = list(preds)[0]
                call_graph.replace_succ(pred_node, node, succ_node)
                call_graph.replace_pred(succ_node, node, pred_node)
            elif node.name == '_module_decorator':
                succs = call_graph.succs(node)
                assert len(succs) == 3
                succ_node = None
                for succ in succs:
                    # it depends on polyphony._module_decorator implementation
                    if succ.name == '_enable' or succ.name == '_disable':
                        continue
                    succ_node = succ
                    break
                assert (succ_node)
                if succ_node.name == '_pure_decorator':
                    # this is @pure ctor
                    succs = call_graph.succs(succ_node)
                    assert len(succs) == 1
                    succ_node = list(succs)[0]
                    succ_node.is_pure = True
                    pure_nodes.append(succ_node)
                succ_node.is_module_ctor = True
                succ_node.caller_lineno = node.caller_lineno
                ctor_nodes.append(succ_node)

                preds = call_graph.preds(node)
                assert len(preds) == 1
                pred_node = list(preds)[0]
                call_graph.replace_succ(pred_node, node, succ_node)
                for pred in call_graph.preds(succ_node).copy():
                    if pred is pred_node:
                        continue
                    call_graph.del_edge(pred, succ_node)
        return pure_nodes, ctor_nodes

    def _set_module_ctor_info(self, call_graph, ctor_nodes):
        for node in ctor_nodes:
            obj = node.vars['self']
            func = RuntimeInfoBuilder.get_method(obj, node.name)
            params = list(inspect.signature(func).parameters.values())[1:]
            args = RuntimeInfoBuilder.get_args(params, node.vars)
            call = MethodCall(node.name, args)
            node.obj = obj
            node.call = call
            node.is_top_module = all([not caller.is_module_ctor for caller in call_graph.preds(node)])
            for succ in call_graph.succs(node):
                if 'self' not in succ.vars:
                    continue
                succ_obj = succ.vars['self']
                func = RuntimeInfoBuilder.get_method(succ_obj, succ.name)
                params = list(inspect.signature(func).parameters.values())[1:]
                args = RuntimeInfoBuilder.get_args(params, succ.vars)
                call = MethodInternalCall(succ.name, succ_obj, args)
                node.internal_calls.append(call)

            self._set_module_field_defaults(obj)

    def _set_module_field_defaults(self, instance):
        # default_values will be used later by the instantiator
        default_values = {}
        specials = {
            '_start', '_stop', 'append_worker',
            '_ctor', '_workers', '_worker_threads', '_submodules', '_module_decorator',
        }
        for name, v in instance.__dict__.items():
            if name in specials or name.startswith('__'):
                continue
            # We have to do deep copy here
            # because a mutable field might be changed by interpret
            default_values[name] = copy.deepcopy(v)
        self.rtinfo.object_defaults[instance] = default_values

    @staticmethod
    def get_method(obj, name):
        if name in obj.__dict__:
            func = obj.__dict__[name]
        elif name in obj.__class__.__dict__:
            func = obj.__class__.__dict__[name]
        elif hasattr(obj, '_module_decorator'):
            if name == '_module_append_worker':
                func = obj.__dict__['append_worker']
            elif name == '_module_start':
                func = obj.__dict__['_start']
            elif name == '_module_stop':
                func = obj.__dict__['_stop']
            else:
                raise InterpretError('get_method {}'.format(name))
        else:
            return None
        if func.__name__ == 'pure_decorator':
            assert func.func
            return func.func
        else:
            return func

    @staticmethod
    def get_args(params, vars):
        cp_vars = vars.copy()
        del cp_vars['self']
        kwargs = RuntimeInfoBuilder.try_copy(cp_vars)
        #print(kwargs)
        #print(params, frame.f_code.co_name)
        return RuntimeInfoBuilder.normalize_args(params, kwargs)

    @staticmethod
    def normalize_args(params, kw):
        kwargs = kw.copy()
        nargs = []
        if not kwargs:
            return []
        for i, param in enumerate(params):
            name = param.name
            if name in kwargs:
                nargs.append((name, kwargs[name]))
                del kwargs[name]
            elif param.default != inspect.Parameter.empty:
                nargs.append((name, param.default))
            elif param.kind == inspect.Parameter.VAR_KEYWORD:
                for name, v in kwargs.items():
                    nargs.append((name, v))
            else:
                raise InterpretError('normalize_args')
        return nargs

    @staticmethod
    def try_copy(orig_dict):
        cp_dict = {}
        for name, v in orig_dict.items():
            #if name.startswith('__'):
            #    continue
            try:
                vv = copy.deepcopy(v)
            except:
                assert False
            cp_dict[name] = vv
        return cp_dict


def _make_pyfuncs(objs):
    pyfuncs = {}
    for name, obj in objs.items():
        if inspect.isfunction(obj) and obj.__name__ == '_pure_decorator':
            assert obj.func
            scope_name = '{}.{}'.format(env.global_scope_name, obj.func.__qualname__)
            scope = env.scopes[scope_name]
            assert scope.is_pure()
            pyfuncs[scope] = obj.func
    return pyfuncs


def _find_module_classes(ctor_nodes):
    classes = set()
    for node in ctor_nodes:
        classes.add(node.obj.__class__)
    return classes


def _find_module_instances(objs, classes):
    instances = {}
    for name, obj in objs.items():
        if isinstance(obj, tuple(classes)):
            instances[name] = obj
            obj._name_ = name
            subinstances = _find_module_instances(obj.__dict__, classes)
            for subname, subobj in subinstances.items():
                instances[name + '.' + subname] = subobj
                subobj._name_ = name + '.' + subname
    return instances


def _find_vars(namespace, dic, visited, namespace_names):
    '''
    vars = {
        'namespace1': {k1:v1, k2:v2, ...},
        'namespace2': {k1:v1, k2:v2, ...},
    }
    '''
    vars = defaultdict(dict)
    namespaces = {}
    for name, obj in dic.items():
        if name != '__name__' and name != '__version__' and name.startswith('__'):
            continue
        namespace_objs = []
        if isinstance(obj, int) or isinstance(obj, str) or isinstance(obj, list) or isinstance(obj, tuple):
            vars[namespace][name] = obj
        elif inspect.isclass(obj):
            if obj.__module__.startswith('polyphony'):
                continue
            namespace_objs.append((name, obj))
            if obj.__module__ in namespace_names and obj.__module__ not in vars:
                mod = inspect.getmodule(obj)
                namespace_objs.append((mod.__name__, mod))
        elif inspect.isfunction(obj) and obj.__name__ == '_module_decorator':
            cls = obj.__dict__['cls']
            assert inspect.isclass(cls)
            namespace_objs.append((name, cls))
            if cls.__module__ in namespace_names and cls.__module__ not in vars:
                mod = inspect.getmodule(cls)
                namespace_objs.append((mod.__name__, mod))
        elif inspect.ismodule(obj) and obj.__name__ in namespace_names:
            namespace_objs.append((name, obj))

        for name, obj in namespace_objs:
            if obj.__name__ in visited:
                continue
            _vars, _namespaces = _find_vars(name, obj.__dict__, namespaces.keys(), namespace_names)
            if _vars:
                vars[namespace][name] = _vars[name]
                if inspect.isclass(obj) and obj.__module__ != '__main__':
                    qual_name = '{}.{}'.format(obj.__module__, obj.__name__)
                else:
                    qual_name = obj.__name__
                namespaces[qual_name] = _vars[name]  # add as origin name
            if _namespaces:
                namespaces.update(_namespaces)
    return vars, namespaces


class PureCtorBuilder(object):
    def __init__(self):
        self.outer_objs = {}

    def process_all(self):
        classes = [scope for scope in env.scopes.values() if scope.is_class() and not scope.is_lib()]
        ctors = [clazz.find_ctor() for clazz in classes]
        results = []
        for ctor in reversed(ctors):
            if not ctor.is_pure():
                continue
            clazz = ctor.parent
            if not clazz.is_instantiated():
                continue
            assert clazz.instance
            assert clazz.inst_name
            self.build_ctor(clazz.instance, ctor)
            results.append(ctor)
        return results

    def build_ctor(self, instance, ctor):
        clazz = ctor.parent
        assert len(clazz.bases) == 1
        base = clazz.bases[0]

        local_type_hints = base.find_ctor().local_type_hints

        if 'self' in local_type_hints:
            self_type_hints = local_type_hints['self']
        else:
            self_type_hints = {}
        self._build_field_var_init(instance, clazz, ctor, self_type_hints)
        self._build_append_worker_call(instance, clazz, ctor, self_type_hints)
        ctor.del_tag('pure')
        LineNumberSetter().process(ctor)

    def _build_field_var_init(self, instance, module, ctor, self_type_hints):
        from ..io import Port, Queue

        self_sym = ctor.find_sym('self')
        assert instance in env.runtime_info.object_defaults
        for name, v in env.runtime_info.object_defaults[instance].items():
            if name in self_type_hints:
                typ = self_type_hints[name]
            else:
                typ = Type.from_expr(v, module)
            if typ.is_object() and typ.get_scope().is_port():
                typ.unfreeze()

            if typ.is_object() and not typ.get_scope().is_port():
                klass_scope = typ.get_scope()
                if klass_scope.find_ctor().is_pure():
                    klass_scope, _ = env.runtime_info.inst2module[v]
                    typ.set_scope(klass_scope)
                klass_scope_sym = klass_scope.parent.gen_sym(klass_scope.orig_name)
                klass_scope_sym.set_type(Type.klass(klass_scope))
                sym = module.add_sym(name, typ=typ.clone())
                orig_obj = instance.__dict__[name]
                calls = env.runtime_info.get_internal_calls(instance)
                for cname, cself, cargs in calls:
                    if cself is orig_obj:
                        args = []
                        for arg_name, arg, in cargs:
                            ir = expr2ir(arg, arg_name, ctor)
                            args.append((arg_name, ir))
                        new = NEW(klass_scope_sym, args, {})
                        dst = ATTR(TEMP(self_sym, Ctx.STORE), sym, Ctx.STORE, attr_scope=module)
                        stm = MOVE(dst, new)
                        stm.lineno = ctor.lineno
                        ctor.entry_block.append_stm(stm)
                        break
            else:
                module.del_sym(name)  # use a new symbol always for the field
                sym = module.add_sym(name)
                if sym.typ.is_undef():
                    sym.set_type(typ)

                # deal with a list of port
                if sym.typ.is_seq() and all([isinstance(item, (Port, Queue)) for item in v]):
                    elem_t = None
                    for i, item in enumerate(v):
                        typ = Type.from_expr(item, module)
                        if elem_t is None:
                            elem_t = typ
                        portsym = module.add_sym(name + '_' + str(i), typ=typ)
                        dst = ATTR(TEMP(self_sym, Ctx.STORE), portsym, Ctx.STORE, attr_scope=module)
                        stm = self._build_move_stm(dst, item, module)
                        assert stm
                        stm.lineno = ctor.lineno
                        ctor.entry_block.append_stm(stm)
                    sym.typ.set_element(elem_t)
                else:
                    dst = ATTR(TEMP(self_sym, Ctx.STORE), sym, Ctx.STORE, attr_scope=module)
                    stm = self._build_move_stm(dst, v, module)
                    assert stm
                    stm.lineno = ctor.lineno
                    ctor.entry_block.append_stm(stm)

    def _build_append_worker_call(self, instance, module, ctor, self_type_hints):
        self_sym = ctor.find_sym('self')
        assert self_sym
        append_worker_sym = module.find_sym('append_worker')
        assert append_worker_sym
        for worker in instance._workers:
            if inspect.ismethod(worker.func):
                worker_scope, _ = env.runtime_info.inst2worker[worker]
                worker_sym = module.find_sym(worker_scope.orig_name)
                worker_var = ATTR(TEMP(self_sym, Ctx.LOAD), worker_sym, Ctx.LOAD)
            else:
                worker_scope, _ = env.runtime_info.inst2worker[worker]
                worker_sym = Scope.global_scope().find_sym(worker_scope.orig_name)
                worker_var = TEMP(worker_sym, Ctx.LOAD)
            args = [(None, worker_var)]
            for arg in worker.args:
                ir = None
                if isinstance(arg, (int, bool, str)):
                    # in this case, arg is already propagated
                    continue
                elif arg.__class__.__module__ == 'polyphony.io':
                    ir = self._port2ir(arg, instance, module, ctor)
                elif arg in instance.__dict__.values():  # is this object field?
                    idx = list(instance.__dict__.values()).index(arg)
                    name = list(instance.__dict__.keys())[idx]
                    attr = module.find_sym(name)
                    ir = ATTR(TEMP(self_sym, Ctx.LOAD), attr, Ctx.LOAD)
                else:
                    ir = expr2ir(arg)
                if ir:
                    args.append((None, ir))
            func = ATTR(TEMP(self_sym, Ctx.LOAD), append_worker_sym, Ctx.LOAD)
            call = CALL(func, args, kwargs={})
            expr = EXPR(call)
            expr.lineno = ctor.lineno
            ctor.entry_block.append_stm(expr)

    def _build_move_stm(self, dst, v, module):
        if dst.symbol().typ.is_scalar():
            assert isinstance(v, (bool, int, str))
            return MOVE(dst, CONST(v))
        elif dst.symbol().typ.is_list():
            assert all([isinstance(item, (bool, int, str)) for item in v])
            items = [CONST(item) for item in v]
            array = ARRAY(items)
            return MOVE(dst, array)
        elif dst.symbol().typ.is_tuple():
            for item in v:
                assert isinstance(item, (bool, int, str))
            items = [CONST(item) for item in v]
            array = ARRAY(items, is_mutable=False)
            return MOVE(dst, array)
        elif dst.symbol().typ.is_object():
            scope = dst.symbol().typ.get_scope()
            if scope.is_port():
                new = self._build_new_port(v, module)
                return MOVE(dst, new)
            assert False
        else:
            assert False

    def _build_new_port(self, port, module):
        #from ..io import Port, Queue
        pnames = inspect.signature(port.__init__).parameters.keys()
        port_args = [(pname, port.__dict__['_' + pname]) for pname in pnames]
        args = [(pname, expr2ir(pvalue, None, module)) for pname, pvalue in port_args]
        port_qualname = port.__module__ + '.' + port.__class__.__name__
        port_scope = env.scopes[port_qualname]
        port_scope_sym = port_scope.parent.gen_sym(port_scope.orig_name)
        port_scope_sym.set_type(Type.klass(port_scope))
        return NEW(port_scope_sym, args, kwargs={})

    def _port2ir(self, port_obj, instance, module, ctor):
        def port_qsym(scope, di, obj):
            for name, field in di.items():
                if obj is field:
                    sym = scope.find_sym(name)
                    assert sym
                    if sym.typ.is_undef():
                        typ = Type.from_expr(field, scope)
                        sym.set_type(typ)
                    return (sym, )
                if isinstance(field, (list, tuple)) and obj in field:
                    idx = field.index(obj)
                    port_name = '{}_{}'.format(name, idx)
                    sym = scope.find_sym(port_name)
                    assert sym
                    assert not sym.typ.is_undef()
                    return (sym, )
            for name, field in di.items():
                if not hasattr(field, '__dict__'):
                    continue
                sym = scope.find_sym(name)
                if not sym:
                    continue
                if sym.typ.is_undef():
                    typ = Type.from_expr(field, scope)
                    sym.set_type(typ)
                assert sym.typ.has_scope()
                scp = sym.typ.get_scope()
                result = port_qsym(scp, field.__dict__, obj)
                if result:
                    return (sym, ) + result
            return None

        def qsym_to_var(qsym, ctx):
            if len(qsym) == 1:
                return TEMP(qsym[0], ctx)
            else:
                exp = qsym_to_var(qsym[:-1], Ctx.LOAD)
                return ATTR(exp, qsym[-1], ctx)

        qsym = port_qsym(module, instance.__dict__, port_obj)
        if qsym:
            self_sym = ctor.find_sym('self')
            qsym = (self_sym,) + qsym
            port_var = qsym_to_var(qsym, Ctx.LOAD)
            return port_var
        else:
            # this port have been created as a local variable in the other scope
            # so we must append an aditional NEW(port) stmt here
            if port_obj in self.outer_objs:
                sym = self.outer_objs[port_obj]
            else:
                sym = ctor.add_temp('local_port')
                typ = Type.from_expr(port_obj, ctor)
                sym.set_type(typ)

                dst = TEMP(sym, Ctx.STORE)
                stm = self._build_move_stm(dst, port_obj, module)
                assert stm
                stm.lineno = ctor.lineno
                ctor.entry_block.append_stm(stm)
                self.outer_objs[port_obj] = sym
            return TEMP(sym, Ctx.LOAD)
        assert False


class PureFuncTypeInferrer(object):
    def __init__(self):
        self.used_pure_node = set()

    def infer_type(self, call, scope):
        assert call.is_a(CALL)
        assert call.func_scope().is_pure()
        if not call.func_scope().return_type:
            call.func_scope().return_type = Type.any_t

        for node in env.runtime_info.pure_nodes:
            if node.caller_lineno != call.lineno:
                continue
            if node in self.used_pure_node:
                continue
            self.used_pure_node.add(node)
            #if not all([type(func_rets[0].arg) is type(ret.arg) for ret in func_rets[1:]]):
            #    return False, Errors.PURE_RETURN_NO_SAME_TYPE
            return True, Type.from_expr(node.ret, scope)
        assert False


class PureFuncExecutor(ConstantOptBase):
    def process_all(self, driver):
        scopes = Scope.get_scopes(bottom_up=True, with_global=True, with_class=True)
        for scope in scopes:
            self.process(scope)

    def _args2tuple(self, args):
        def arg2expr(arg):
            if arg.is_a(CONST):
                return arg.value
            elif arg.is_a(ARRAY):
                items = self._args2tuple(arg.items)
                if not items:
                    return None
                if arg.repeat.value > 1:
                    items = items * arg.repeat.value
                return items
            elif arg.is_a(TEMP):
                stms = self.scope.usedef.get_stms_defining(arg.symbol())
                if not stms:
                    return None
                assert len(stms) == 1
                stm = list(stms)[0]
                return arg2expr(stm.src)
            else:
                return None
        values = [arg2expr(self.visit(arg)) for arg in args]
        if None in values:
            return None
        return tuple(values)

    def visit_CALL(self, ir):
        if not ir.func_scope().is_pure():
            return ir
        assert env.config.enable_pure
        assert ir.func_scope().parent.is_global()
        args = self._args2tuple([arg for _, arg in ir.args])
        if args is None:
            fail(self.current_stm, Errors.PURE_ARGS_MUST_BE_CONST)

        assert ir.func_scope() in env.runtime_info.pyfuncs
        pyfunc = env.runtime_info.pyfuncs[ir.func_scope()]
        expr = pyfunc(*args)
        return expr2ir(expr, scope=self.scope)

    def visit_SYSCALL(self, ir):
        return super().visit_CALL(ir)

    def visit_NEW(self, ir):
        return super().visit_CALL(ir)

    def visit_MOVE(self, ir):
        ir.src = self.visit(ir.src)
        if ir.src.is_a(ARRAY):
            memnode = env.memref_graph.node(ir.dst.symbol())
            source = memnode.single_source()
            if source.is_pure() and not source.initstm:  # and not memnode.preds:
                source.initstm = ir
                if ir.src.items[0].is_a(CONST):
                    item_t = Type.from_expr(ir.src.items[0].value, self.scope)
                else:
                    assert False
                if ir.src.is_mutable:
                    t = Type.list(item_t, source)
                else:
                    t = Type.tuple(item_t, source, len(ir.src.items))
                ir.src.sym.set_type(t)