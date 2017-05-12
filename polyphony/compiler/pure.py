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
from .ir import expr2ir, Ctx, CONST, TEMP, ATTR, ARRAY, CALL, NEW, MOVE, EXPR
from .setlineno import LineNumberSetter
from .type import Type


def interpret(source, file_name=''):
    stdout = sys.stdout
    sys.stdout = None
    objs = {}
    rtinfo = RuntimeInfo()
    threading.setprofile(rtinfo._profile_func)
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
    rtinfo.pyfuncs = _make_pyfuncs(objs)
    module_classes = _find_module_classes(objs)
    for cls in module_classes:
        pyfuncs = _make_pyfuncs(cls.__dict__)
        rtinfo.pyfuncs.update(pyfuncs)
    instances = _find_module_instances(objs, module_classes)
    rtinfo.module_classes = module_classes
    rtinfo.module_instances = instances
    namespace_names = [scp.name for scp in env.scopes.values() if scp.is_namespace() and not scp.is_global()]
    rtinfo.global_vars = _find_vars(objs, namespace_names)
    env.runtime_info = rtinfo


def _do_interpret(source, file_name, objs):
    if file_name:
        dir_name = os.path.dirname(file_name)
        sys.path.append(dir_name)
    code = compile(source, file_name, 'exec')
    th = threading.current_thread()
    th.exc_info = None
    try:
        exec(code, objs)
    except Exception:
        th.exc_info = sys.exc_info()


MethodCall = namedtuple('MethodCall', ('name', 'args'))
MethodReturn = namedtuple('MethodReturn', ('name', 'locals'))
MethodInternalCall = namedtuple('MethodInternalCall', ('name', 'self', 'args', 'caller_info'))
FuncReturn = namedtuple('FuncReturn', ('name', 'func', 'arg'))


class RuntimeInfo(object):
    def __init__(self):
        self.pure_depth = 0
        self.pure_method_calls = defaultdict(list)
        self.pure_method_returns = defaultdict(list)
        self.pure_method_internal_calls = defaultdict(list)
        self.object_defaults = {}
        self.current_obj = None
        self.line_stack = defaultdict(int)
        self.pure_func_returns = defaultdict(list)

    def _profile_func(self, frame, event, arg):
        if self.pure_depth:
            if event == 'call':
                if len(frame.f_code.co_varnames) and 'self' == frame.f_code.co_varnames[0]:
                    obj = frame.f_locals['self']
                    self._profile_pure_method_call(obj, frame)
                else:
                    pass  # nothing to do ?
                self.pure_depth += 1
            elif event == 'return':
                if len(frame.f_code.co_varnames) and 'self' == frame.f_code.co_varnames[0]:
                    obj = frame.f_locals['self']
                    self._profile_pure_method_return(obj, frame, arg)
                else:
                    self._profile_pure_func_return(frame, arg)
                self.pure_depth -= 1
        elif event == 'call' and frame.f_code.co_name == '_pure_decorator':
            self.pure_depth += 1

    def _profile_pure_method_call(self, obj, frame):
        if self.pure_depth == 1:
            msg = 'PURE METHOD CALL {} {} {}:{}'.format(frame.f_code.co_name, frame.f_code.co_varnames, frame.f_code.co_filename, frame.f_lineno)
            print(msg)
            self.current_obj = obj
            func = RuntimeInfo.get_method(obj, frame.f_code.co_name)
            if func:
                params = list(inspect.signature(func).parameters.values())[1:]
                args = RuntimeInfo.get_args(params, frame)
                call = MethodCall(frame.f_code.co_name, args)
                self.pure_method_calls[self.current_obj].append(call)
        elif self.pure_depth == 2:
            msg = 'PURE METHOD INTERNAL CALL {} {} {}:{}'.format(frame.f_code.co_name, frame.f_code.co_varnames, frame.f_code.co_filename, frame.f_lineno)
            print(msg)
            func = RuntimeInfo.get_method(obj, frame.f_code.co_name)
            if func:
                params = list(inspect.signature(func).parameters.values())[1:]
                args = RuntimeInfo.get_args(params, frame)
                caller_info = (frame.f_code.co_filename, frame.f_back.f_lineno)
                call = MethodInternalCall(frame.f_code.co_name, obj, args, caller_info)
                self.pure_method_internal_calls[self.current_obj].append(call)

    def _profile_pure_method_return(self, obj, frame, arg):
        if self.pure_depth == 2:
            msg = 'PURE RET {} {}:{}'.format(frame.f_code.co_name, frame.f_code.co_filename, frame.f_lineno)
            print(msg, self.pure_depth)
            cp_locals = frame.f_locals.copy()
            del cp_locals['self']
            defaults = self.try_copy(cp_locals)
            ret = MethodReturn(frame.f_code.co_name, defaults)
            self.pure_method_returns[self.current_obj].append(ret)
            if self.current_obj is not obj:
                raise InterpretError('current_obj')

            if frame.f_code.co_name == '__init__':
                self._set_module_field_defaults(obj)

    def _get_caller_context(self, frame):
        f = frame
        nums = []
        while f:
            nums.append(f.f_lineno)
            f = f.f_back
        return tuple(nums)

    def _profile_pure_func_return(self, frame, arg):
        if self.pure_depth == 2:
            caller_context = self._get_caller_context(frame.f_back.f_back)
            caller_num = self.line_stack[caller_context]
            self.line_stack[caller_context] += 1
            purefunc = frame.f_back.f_locals['func']
            caller_id = (caller_context[0], caller_num)
            ret = FuncReturn(frame.f_code.co_name, purefunc, arg)
            self.pure_func_returns[caller_id].append(ret)

    def _set_module_field_defaults(self, instance):
        # default_values will be used later by the instantiator
        default_values = {}
        specials = {
            '_start', '_stop', 'append_worker',
            '_ctor', '_workers', '_module_decorator'
        }
        for name, v in instance.__dict__.items():
            if name in specials or name.startswith('__'):
                continue
            # We have to do deep copy here
            # because a mutable field might be changed by interpret
            default_values[name] = copy.deepcopy(v)
        self.object_defaults[instance] = default_values

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
    def get_args(params, frame):
        cp_locals = frame.f_locals.copy()
        del cp_locals['self']
        kwargs = RuntimeInfo.try_copy(cp_locals)
        print(kwargs)
        print(params, frame.f_code.co_name)
        return RuntimeInfo.normalize_args(params, kwargs)

    @staticmethod
    def normalize_args(params, kw):
        kwargs = kw.copy()
        nargs = []
        if not kwargs:
            return []
        for i, param in enumerate(params):
            print()
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


def _find_module_classes(objs):
    classes = set()
    for name, obj in objs.items():
        if inspect.isfunction(obj) and obj.__name__ == '_module_decorator':
            assert inspect.isclass(obj.cls)
            classes.add(obj.cls)
    return classes


def _find_module_instances(objs, classes):
    instances = {}
    for name, obj in objs.items():
        if isinstance(obj, tuple(classes)):
            instances[name] = obj
    return instances


def _find_vars(dic, namespace_names):
    vars = {}
    for name, obj in dic.items():
        if name != '__name__' and name != '__version__' and name.startswith('__'):
            continue
        if isinstance(obj, int) or isinstance(obj, str) or isinstance(obj, list) or isinstance(obj, tuple):
            vars[name] = obj
        elif inspect.isclass(obj):
            _vars = _find_vars(obj.__dict__, namespace_names)
            if _vars:
                vars[name] = _vars
        elif inspect.isfunction(obj) and obj.__name__ == '_module_decorator':
            cls = obj.__dict__['cls']
            assert inspect.isclass(cls)
            _vars = _find_vars(cls.__dict__, namespace_names)
            if _vars:
                vars[name] = _vars
        elif inspect.ismodule(obj) and obj.__name__ in namespace_names:
            _vars = _find_vars_in_libs(obj.__name__, obj.__dict__, namespace_names)
            if _vars:
                vars[name] = _vars
    return vars


def _find_vars_in_libs(libname, dic, namespace_names):
    if libname == 'polyphony.compiler':
        return None
    vars = {}
    for name, obj in dic.items():
        if name != '__name__' and name != '__version__' and name.startswith('_'):
            continue
        if isinstance(obj, int) or isinstance(obj, str) or isinstance(obj, list) or isinstance(obj, tuple):
            vars[name] = obj
        elif inspect.isclass(obj):
            _vars = _find_vars(obj.__dict__, namespace_names)
            if _vars:
                vars[name] = _vars
        elif inspect.ismodule(obj) and obj.__name__ in namespace_names:
            _vars = _find_vars_in_libs(obj.__name__, obj.__dict__, namespace_names)
            if _vars:
                vars[name] = _vars
    return vars


class PureCtorBuilder(object):
    def __init__(self):
        self.outer_objs = {}

    def process_all(self):
        classes = [scope for scope in env.scopes.values() if scope.is_class() and not scope.is_lib()]
        ctors = [clazz.find_ctor() for clazz in classes]
        results = []
        for ctor in ctors:
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
                sym = module.add_sym(name)
                sym.set_type(typ)
                orig_obj = instance.__dict__[name]
                calls = env.runtime_info.pure_method_internal_calls[instance]
                for cname, cself, cargs, caller_info in calls:
                    if cself is orig_obj:
                        args = []
                        for arg_name, arg, in cargs:
                            ir = expr2ir(arg, arg_name, ctor)
                            args.append((arg_name, ir))
                        new = NEW(klass_scope, args, {})
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
                        portsym = module.add_sym(name + '_' + str(i))
                        typ = Type.from_expr(item, module)
                        if elem_t is None:
                            elem_t = typ
                        portsym.set_type(typ)
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
            worker_func = expr2ir(worker.func, worker.func.__qualname__, module)
            args = [(None, worker_func)]
            for arg in worker.args:
                if hasattr(arg, '__module__'):
                    if arg.__module__ == 'polyphony.io':
                        ir = self._port2ir(arg, instance, module, ctor)
                    else:
                        assert False
                else:
                    ir = expr2ir(arg)
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
        return NEW(port_scope, args, kwargs={})

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
            method_rets = env.runtime_info.pure_method_returns[instance]
            for method_name, method_locals in method_rets:
                if method_name != env.ctor_name:
                    continue
                for name, val in method_locals.items():
                    if val is not port_obj:
                        continue
                    # make new port name if the port name has been used as a field
                    if name in instance.__dict__:
                        name = name + '_'
                    sym = ctor.find_sym(name)
                    if not sym:
                        sym = ctor.add_sym(name)
                        typ = Type.from_expr(port_obj, ctor)
                        sym.set_type(typ)

                        dst = TEMP(sym, Ctx.LOAD)
                        stm = self._build_move_stm(dst, port_obj, module)
                        assert stm
                        stm.lineno = ctor.lineno
                        ctor.entry_block.append_stm(stm)
                    return TEMP(sym, Ctx.LOAD)
            # this port have been created as a local variable in the other scope
            # so we must append an aditional NEW(port) stmt here
            if port_obj in self.outer_objs:
                sym = self.outer_objs[port_obj]
            else:
                sym = ctor.add_temp('local_port')
                typ = Type.from_expr(port_obj, ctor)
                sym.set_type(typ)

                dst = TEMP(sym, Ctx.LOAD)
                stm = self._build_move_stm(dst, port_obj, module)
                assert stm
                stm.lineno = ctor.lineno
                ctor.entry_block.append_stm(stm)
                self.outer_objs[port_obj] = sym
            return TEMP(sym, Ctx.LOAD)
        assert False


class PureFuncTypeInferrer(object):
    def __init__(self):
        self.used_caller_ids = set()

    def infer_type(self, call, scope):
        assert call.is_a(CALL)
        assert call.func_scope.is_pure()
        if not call.func_scope.return_type:
            call.func_scope.return_type = Type.any_t
        pure_func_returns = env.runtime_info.pure_func_returns
        for caller_id, func_rets in pure_func_returns.items():
            if caller_id[0] != call.lineno:
                continue
            if caller_id in self.used_caller_ids:
                continue
            self.used_caller_ids.add(caller_id)
            if not all([type(func_rets[0].arg) is type(ret.arg) for ret in func_rets[1:]]):
                return False, Errors.PURE_RETURN_NO_SAME_TYPE
            return True, Type.from_expr(func_rets[0].arg, scope)
        assert False


class PureFuncExecutor(ConstantOptBase):
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
        if not ir.func_scope.is_pure():
            return ir
        assert env.enable_pure
        assert ir.func_scope.parent.is_global()
        args = self._args2tuple([arg for _, arg in ir.args])
        if args is None:
            fail(self.current_stm, Errors.PURE_ARGS_MUST_BE_CONST)

        assert ir.func_scope in env.runtime_info.pyfuncs
        pyfunc = env.runtime_info.pyfuncs[ir.func_scope]
        expr = pyfunc(*args)
        return expr2ir(expr)

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
