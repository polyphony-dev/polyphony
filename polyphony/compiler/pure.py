import copy
import inspect
import os
import sys
import threading
from collections import namedtuple, defaultdict
from .common import fail
from .constopt import ConstantOptBase, eval_binop
from .errors import Errors
from .env import env
#from .ir import *
from .ir import expr2ir, Ctx, CONST, TEMP, ATTR, ARRAY, CALL, NEW, MOVE, EXPR
from .setlineno import LineNumberSetter
from .symbol import Symbol
from .type import Type


class InterpretError(Exception):
    pass


def interpret(source, file_name):
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
    _set_pyfunc(objs)
    module_classes = _find_module_classes(objs)
    instances = _find_module_instances(objs, module_classes)
    env.module_classes = module_classes
    env.module_instances = instances
    env.runtime_info = rtinfo


def _do_interpret(source, file_name, objs):
    dir_name = os.path.dirname(file_name)
    sys.path.append(dir_name)
    code = compile(source, file_name, 'exec')
    try:
        exec(code, objs)
    except InterpretError as e:
        raise e
    except Exception as e:
        pass


MethodCall = namedtuple('MethodCall', ('name', 'args'))
MethodReturn = namedtuple('MethodReturn', ('name', 'locals'))
MethodInternalCall = namedtuple('MethodInternalCall', ('name', 'self', 'args', 'caller_info'))


class RuntimeInfo(object):
    def __init__(self):
        self.pure_depth = 0
        self.pure_method_calls = defaultdict(list)
        self.pure_method_returns = defaultdict(list)
        self.pure_method_internal_calls = defaultdict(list)
        self.object_defaults = {}
        self.current_obj = None
        self.base_obj = None

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
                    pass  # nothing to do ?
                self.pure_depth -= 1
        elif event == 'call' and frame.f_code.co_name == '_pure_decorator':
            self.pure_depth += 1

    def _profile_pure_method_call(self, obj, frame):

        if self.pure_depth == 1:
            msg = 'PURE METHOD CALL {} {} {}:{}'.format(frame.f_code.co_name, frame.f_code.co_varnames, frame.f_code.co_filename, frame.f_lineno)
            print(msg)
            self.current_obj = obj
            self.base_obj = obj
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


def _set_pyfunc(objs):
    for name, obj in objs.items():
        if inspect.isfunction(obj) and obj.__name__ == '_pure_decorator':
            assert obj.func
            scope_name = '{}.{}'.format(env.global_scope_name, obj.func.__qualname__)
            scope = env.scopes[scope_name]
            assert scope.is_pure()
            scope.pyfunc = obj.func


def _find_module_classes(objs):
    classes = set()
    for name, obj in objs.items():
        if inspect.isfunction(obj) and obj.__name__ == '_module_decorator':
            assert inspect.isclass(obj.cls)
            classes.add(obj.cls)
            _set_pyfunc(obj.cls.__dict__)
    return classes


def _find_module_instances(objs, classes):
    instances = {}
    for name, obj in objs.items():
        if isinstance(obj, tuple(classes)):
            instances[name] = obj
    return instances


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
        #self._build_port_init(instance, module, ctor, self_types)
        self._build_local_var_init(instance, clazz, ctor, local_type_hints)
        self._build_append_worker_call(instance, clazz, ctor, self_type_hints)
        ctor.del_tag('pure')
        LineNumberSetter().process(ctor)

    def _build_field_var_init(self, instance, module, ctor, self_type_hints):
        self_sym = ctor.find_sym('self')
        assert instance in env.runtime_info.object_defaults
        for name, v in env.runtime_info.object_defaults[instance].items():
            if name in self_type_hints:
                typ = self_type_hints[name]
            else:
                typ = self._type_from_expr(v, module)
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
                dst = ATTR(TEMP(self_sym, Ctx.STORE), sym, Ctx.STORE, attr_scope=module)
                stm = self._build_move_stm(dst, v, module)
                assert stm
                stm.lineno = ctor.lineno
                ctor.entry_block.append_stm(stm)

    def _build_local_var_init(self, instance, module, ctor, local_type_hints):
        from ..io import Port, Queue
        method_rets = env.runtime_info.pure_method_returns[instance]
        for method_name, method_locals in method_rets:
            if method_name != env.ctor_name:
                continue
            for name, val in method_locals.items():
                if isinstance(val, (Port, Queue)):
                    sym = ctor.add_sym(name)
                    typ = self._type_from_expr(val, ctor)
                    sym.set_type(typ)
                    dst = TEMP(sym, Ctx.LOAD)
                    stm = self._build_move_stm(dst, val, module)
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
            for item in v:
                assert isinstance(item, (bool, int, str))
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
                    if not sym:
                        sym = scope.add_sym(name)
                    if sym.typ.is_undef():
                        typ = self._type_from_expr(field, scope)
                        sym.set_type(typ)
                    return (sym, )
            for name, field in di.items():
                if not hasattr(field, '__dict__'):
                    continue
                sym = scope.find_sym(name)
                if not sym:
                    continue
                if sym.typ.is_undef():
                    typ = self._type_from_expr(field, scope)
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
                    sym = ctor.find_sym(name)
                    if not sym:
                        sym = ctor.add_sym(name)
                        typ = self._type_from_expr(port_obj, ctor)
                        sym.set_type(typ)
                    return TEMP(sym, Ctx.LOAD)
            # this port have been created as a local variable in the other scope
            # so we must append an aditional NEW(port) stmt here
            if port_obj in self.outer_objs:
                sym = self.outer_objs[port_obj]
            else:
                sym = ctor.add_temp('tmp_port')
                typ = self._type_from_expr(port_obj, ctor)
                sym.set_type(typ)

                dst = TEMP(sym, Ctx.LOAD)
                stm = self._build_move_stm(dst, port_obj, module)
                assert stm
                stm.lineno = ctor.lineno
                ctor.entry_block.append_stm(stm)
                self.outer_objs[port_obj] = sym
            return TEMP(sym, Ctx.LOAD)
        assert False

    # def _dtype_symbol(self, dtype, scope):
    #     sym = scope.find_sym(dtype.__name__)
    #     if not sym:
    #         if dtype is bool:
    #             t = Type.bool_t
    #         elif hasattr(dtype, 'base_type'):
    #             scope_name = 'polyphony.typing.{}'.format(dtype.__name__)
    #             type_scope = env.scopes[scope_name]
    #             t = Type.klass(type_scope)
    #         sym = scope.add_sym(dtype.__name__)
    #         sym.set_type(t)
    #     return sym

    def _type_from_expr(self, val, module):
        if isinstance(val, bool):
            return Type.bool_t
        elif isinstance(val, int):
            return Type.int()
        elif isinstance(val, str):
            return Type.str_t
        elif isinstance(val, list):
            t = Type.list(Type.undef_t, None)
            t.attrs['length'] = len(val)
            return t
        elif isinstance(val, tuple):
            t = Type.list(Type.undef_t, None, len(val))
            return t
        elif hasattr(val, '__class__'):
            t = Type.from_annotation(val.__class__.__name__, module)
            t.unfreeze()
            return t
        else:
            assert False


class PureFuncExecutor(ConstantOptBase):
    def _args2tuple(self, args):
        values = []
        for arg in args:
            a = self.visit(arg)
            if a.is_a(CONST):
                values.append(a.value)
            elif a.is_a(ARRAY):
                items = self._args2tuple(a.items)
                if not items:
                    return None
                values.append(items)
            else:
                return None
        return tuple(values)

    def visit_CALL(self, ir):
        if not isinstance(ir.func.symbol(), Symbol):
            return ir
        if not ir.func.symbol().typ.is_function():
            return ir
        assert ir.func.symbol().typ.has_scope()
        scope = ir.func.symbol().typ.get_scope()
        if not scope.is_pure():
            return ir
        if not env.enable_pure:
            fail(self.current_stm, Errors.PURE_IS_DISABLED)
        if not scope.parent.is_global():
            fail(self.current_stm, Errors.PURE_MUST_BE_GLOBAL)
        assert scope.pyfunc
        args = self._args2tuple([arg for _, arg in ir.args])
        if args is None:
            fail(self.current_stm, Errors.PURE_ARGS_MUST_BE_CONST)
        expr = scope.pyfunc(*args)
        return expr2ir(expr)

    def visit_SYSCALL(self, ir):
        return super().visit_CALL(ir)

    def visit_NEW(self, ir):
        return super().visit_CALL(ir)

    def visit_BINOP(self, ir):
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)
        if ir.left.is_a(CONST) and ir.right.is_a(CONST):
            return CONST(eval_binop(ir, self))
        if ir.left.is_a(ARRAY):
            if ir.op == 'Mult' and ir.right.is_a(CONST):
                array = ir.left
                array.items *= ir.right.value
                return array
        return ir

