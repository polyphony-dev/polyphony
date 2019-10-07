from collections import deque
from .common import fail, warn
from .errors import Errors, Warnings
from .irvisitor import IRVisitor
from .ir import *
from .pure import PureFuncTypeInferrer
from .scope import Scope
from .type import Type
from .typeeval import TypeEvaluator
from .env import env
from .symbol import Symbol
import logging
logger = logging.getLogger(__name__)


def type_error(ir, err_id, args=None):
    fail(ir, err_id, args)


class RejectPropagation(Exception):
    pass


class TypePropagation(IRVisitor):
    def process_all(self):
        self.typed = []
        self.pure_type_inferrer = PureFuncTypeInferrer()
        self.worklist = deque([Scope.global_scope()])
        while self.worklist:
            scope = self.worklist.popleft()
            if scope.is_lib():
                if scope.is_specialized():
                    self.typed.append(scope)
                continue
            elif scope.is_directory():
                continue
            if scope.is_function() and scope.return_type is None:
                scope.return_type = Type.undef()
            try:
                self.process(scope)
            except RejectPropagation as r:
                self.worklist.append(scope)
                continue
            #print(scope.name)
            assert scope not in self.typed
            self.typed.append(scope)
        return self.typed

    def _add_scope(self, scope):
        if scope not in self.typed and scope not in self.worklist:
            self.worklist.append(scope)

    def visit_UNOP(self, ir):
        return self.visit(ir.exp)

    def visit_BINOP(self, ir):
        l_t = self.visit(ir.left)
        r_t = self.visit(ir.right)
        if l_t.is_bool() and r_t.is_bool() and not ir.op.startswith('Bit'):
            return Type.int(2)
        return l_t

    def visit_RELOP(self, ir):
        self.visit(ir.left)
        self.visit(ir.right)
        return Type.bool()

    def visit_CONDOP(self, ir):
        self.visit(ir.cond)
        ltype = self.visit(ir.left)
        self.visit(ir.right)
        return ltype

    def _convert_call(self, ir):
        clazz = ir.func.symbol().typ.get_scope()
        if clazz:
            if clazz.is_port():
                fun_name = 'wr' if ir.args else 'rd'
            else:
                fun_name = env.callop_name
            func_sym = clazz.find_sym(fun_name)
            if not func_sym:
                fail(self.current_stm, Errors.IS_NOT_CALLABLE, [clazz.name])
            assert func_sym.typ.is_function()
            ir.func = ATTR(ir.func, clazz.symbols[fun_name], Ctx.LOAD)
            ir.func.funcall = True
            ir.func.attr_scope = clazz

    def visit_CALL(self, ir):
        self.visit(ir.func)
        func_scope = ir.func_scope()
        if func_scope.is_method():
            params = func_scope.params[1:]
        else:
            params = func_scope.params[:]
        arg_types = [self.visit(arg) for _, arg in ir.args]
        if params:
            assert func_scope.is_specialized()
        for p, arg_t in zip(params, arg_types):
            self._propagate(p.sym, arg_t)
        self._add_scope(func_scope)
        return func_scope.return_type

    def visit_NEW(self, ir):
        func_scope = ir.func_scope()
        ret_t = Type.object(func_scope)
        func_scope.return_type = ret_t
        ctor = func_scope.find_ctor()
        params = ctor.params[1:]
        arg_types = [self.visit(arg) for _, arg in ir.args]
        if params:
            assert func_scope.is_specialized()
        for p, arg_t in zip(params, arg_types):
            self._propagate(p.sym, arg_t)
        self._add_scope(func_scope)
        self._add_scope(ctor)
        return ret_t

    def visit_SYSCALL(self, ir):
        ir.args = self._normalize_syscall_args(ir.sym.name, ir.args, ir.kwargs)
        for _, arg in ir.args:
            self.visit(arg)
        if ir.sym.name == 'polyphony.io.flipped':
            temp = ir.args[0][1]
            if temp.symbol().typ.is_undef():
                raise RejectPropagation(ir)
            arg_scope = temp.symbol().typ.get_scope()
            return Type.object(arg_scope)
        else:
            assert ir.sym.typ.is_function()
            return ir.sym.typ.get_return_type()

    def visit_CONST(self, ir):
        if isinstance(ir.value, bool):
            return Type.bool()
        elif isinstance(ir.value, int):
            return Type.int()
        elif isinstance(ir.value, str):
            return Type.str()
        elif ir.value is None:
            return Type.int()
        else:
            type_error(self.current_stm, Errors.UNSUPPORTED_LETERAL_TYPE,
                       [repr(ir)])

    def visit_TEMP(self, ir):
        if ir.sym.typ.is_undef() and ir.sym.is_static():
            if ir.sym.ancestor:
                if ir.sym.ancestor.typ.is_undef():
                    self._add_scope(ir.sym.ancestor.scope)
                    raise RejectPropagation(ir)
                ir.sym.set_type(ir.sym.ancestor.typ.clone())
            elif self.scope is not ir.sym.scope:
                self._add_scope(ir.sym.scope)
        elif ir.sym.typ.is_class() and ir.sym.typ.get_scope().is_typeclass():
            t = Type.from_ir(ir)
            if t.is_object():
                ir.sym.typ.set_scope(t.get_scope())
            else:
                type_scope, args = Type.to_scope(t)
                ir.sym.typ.set_scope(type_scope)
                ir.sym.typ.set_typeargs(args)
        elif ir.funcall is False and ir.sym.typ.is_function():
            func_scope = ir.sym.typ.get_scope()
            self._add_scope(func_scope)
        return ir.sym.typ

    def visit_ATTR(self, ir):
        exptyp = self.visit(ir.exp)
        if exptyp.is_object() or exptyp.is_class() or exptyp.is_namespace() or exptyp.is_port():
            attr_scope = exptyp.get_scope()
            ir.attr_scope = attr_scope
            self._add_scope(attr_scope)

        if ir.attr_scope:
            assert ir.attr_scope.is_containable()
            if isinstance(ir.attr, str):
                if not ir.attr_scope.has_sym(ir.attr):
                    type_error(self.current_stm, Errors.UNKNOWN_ATTRIBUTE,
                               [ir.attr])
                ir.attr = ir.attr_scope.find_sym(ir.attr)
            elif ir.attr_scope is not ir.attr.scope:
                ir.attr = ir.attr_scope.find_sym(ir.attr.name)
            assert ir.attr
            if ir.attr.typ.is_object():
                ir.attr.add_tag('subobject')
            if ir.exp.symbol().typ.is_object() and ir.exp.symbol().name != env.self_name and self.scope.is_worker():
                ir.exp.symbol().add_tag('subobject')
            if ir.funcall is False and ir.attr.typ.is_function():
                func_scope = ir.attr.typ.get_scope()
                self._add_scope(func_scope)
            return ir.attr.typ

        raise RejectPropagation(ir)

    def visit_MREF(self, ir):
        mem_t = self.visit(ir.mem)
        if mem_t.is_undef():
            raise RejectPropagation(ir)
        self.visit(ir.offset)
        if mem_t.is_class() and mem_t.get_scope().is_typeclass():
            t = Type.from_ir(ir)
            if t.is_object():
                mem_t.set_scope(t.get_scope())
            else:
                type_scope, args = Type.to_scope(t)
                mem_t.set_scope(type_scope)
                mem_t.set_typeargs(args)
            return mem_t
        elif not mem_t.is_seq():
            type_error(self.current_stm, Errors.IS_NOT_SUBSCRIPTABLE,
                       [ir.mem])
        elif mem_t.is_tuple():
            # TODO: Return union type if the offset is variable
            return mem_t.get_element()
        return mem_t.get_element()

    def visit_MSTORE(self, ir):
        mem_t = self.visit(ir.mem)
        if mem_t.is_undef():
            raise RejectPropagation(ir)
        self.visit(ir.offset)
        if not mem_t.is_seq():
            type_error(self.current_stm, Errors.IS_NOT_SUBSCRIPTABLE,
                       [ir.mem])
        return mem_t

    def visit_ARRAY(self, ir):
        if not ir.repeat.is_a(CONST):
            self.visit(ir.repeat)
        if not ir.sym:
            ir.sym = self.scope.add_temp('@array')
        #self.visit(ir.repeat)
        item_t = None
        if self.current_stm.dst.is_a([TEMP, ATTR]):
            dsttyp = self.current_stm.dst.symbol().typ
            if dsttyp.is_seq() and dsttyp.get_element().is_explicit():
                item_t = dsttyp.get_element().clone()
        if item_t is None:
            item_typs = [self.visit(item) for item in ir.items]
            if self.current_stm.src == ir:
                if any([t.is_undef() for t in item_typs]):
                    raise RejectPropagation(ir)

            if item_typs and all([Type.is_assignable(item_typs[0], item_t) for item_t in item_typs]):
                if item_typs[0].is_scalar() and item_typs[0].is_int():
                    maxwidth = max([item_t.get_width() for item_t in item_typs])
                    signed = any([item_t.has_signed() and item_t.get_signed() for item_t in item_typs])
                    item_t = Type.int(maxwidth, signed)
                else:
                    item_t = item_typs[0]
            else:
                assert False  # TODO:
        if ir.sym.typ.is_seq():
            memnode = ir.sym.typ.get_memnode()
        else:
            memnode = None
        if ir.is_mutable:
            t = Type.list(item_t, memnode)
        else:
            if ir.repeat.is_a(CONST):
                t = Type.tuple(item_t, memnode, len(ir.items) * ir.repeat.value)
            else:
                t = Type.tuple(item_t, memnode, Type.ANY_LENGTH)
        self._propagate(ir.sym, t)
        return t

    def visit_EXPR(self, ir):
        self.visit(ir.exp)

    def visit_CJUMP(self, ir):
        self.visit(ir.exp)

    def visit_MCJUMP(self, ir):
        for cond in ir.conds:
            self.visit(cond)

    def visit_JUMP(self, ir):
        pass

    def visit_RET(self, ir):
        typ = self.visit(ir.exp)
        self.scope.return_type = typ

    def visit_MOVE(self, ir):
        src_typ = self.visit(ir.src)
        if src_typ.is_undef():
            raise RejectPropagation(ir)
        dst_typ = self.visit(ir.dst)

        if ir.dst.is_a([TEMP, ATTR]):
            if not isinstance(ir.dst.symbol(), Symbol):
                # the type of object has not inferenced yet
                raise RejectPropagation(ir)
            self._propagate(ir.dst.symbol(), src_typ.clone())
        elif ir.dst.is_a(ARRAY):
            if src_typ.is_undef():
                # the type of object has not inferenced yet
                raise RejectPropagation(ir)
            if not src_typ.is_tuple() or not dst_typ.is_tuple():
                raise RejectPropagation(ir)
            elem_t = src_typ.get_element()
            for item in ir.dst.items:
                assert item.is_a([TEMP, ATTR, MREF])
                if item.is_a([TEMP, ATTR]):
                    self._propagate(item.symbol(), elem_t.clone())
                elif item.is_a(MREF):
                    item.mem.symbol().typ.set_element(elem_t)
        elif ir.dst.is_a(MREF):
            pass
        else:
            assert False
        # check mutable method
        if (self.scope.is_method() and ir.dst.is_a(ATTR) and
                ir.dst.head().name == env.self_name and
                not self.scope.is_mutable()):
            self.scope.add_tag('mutable')

    def visit_PHI(self, ir):
        arg_types = [self.visit(arg) for arg in ir.args]
        for arg_t in arg_types:
            self._propagate(ir.var.symbol(), arg_t.clone())

    def visit_UPHI(self, ir):
        self.visit_PHI(ir)

    def visit_LPHI(self, ir):
        self.visit_PHI(ir)

    def _normalize_args(self, func_name, params, args, kwargs):
        nargs = []
        if len(params) < len(args):
            nargs = args[:]
            for name, arg in kwargs.items():
                nargs.append((name, arg))
            kwargs.clear()
            return nargs
        for i, param in enumerate(params):
            name = param.copy.name
            if i < len(args):
                nargs.append((name, args[i][1]))
            elif name in kwargs:
                nargs.append((name, kwargs[name]))
            elif param.defval:
                nargs.append((name, param.defval))
            else:
                type_error(self.current_stm, Errors.MISSING_REQUIRED_ARG_N,
                           [func_name, param.copy.name])
        kwargs.clear()
        return nargs

    def _normalize_syscall_args(self, func_name, args, kwargs):
        return args

    def _propagate(self, sym, typ):
        if sym.typ.is_undef() and typ.is_undef():
            return
        assert not typ.is_undef()
        if not Type.can_propagate(sym.typ, typ):
            return
        if sym.typ.is_explicit():
            typ = Type.propagate(sym.typ, typ)
        else:
            if sym.typ != typ:
                logger.debug(f'typeprop {sym.name}: {sym.typ} -> {typ}')
        sym.set_type(typ)


class EarlyTypePropagation(TypePropagation):
    def visit_CALL(self, ir):
        self.visit(ir.func)
        if ir.func.is_a(TEMP):
            func_name = ir.func.symbol().orig_name()
            t = ir.func.symbol().typ
            if t.is_object() or t.is_port():
                self._convert_call(ir)
            elif t.is_function():
                assert t.has_scope()
            else:
                type_error(self.current_stm, Errors.IS_NOT_CALLABLE,
                           [func_name])
        elif ir.func.is_a(ATTR):
            if not ir.func.attr_scope:
                assert False
                raise RejectPropagation(ir)
            func_name = ir.func.symbol().orig_name()
            t = ir.func.symbol().typ
            if t.is_object() or t.is_port():
                self._convert_call(ir)
            if t.is_undef():
                assert False
                raise RejectPropagation(ir)
            if ir.func_scope().is_mutable():
                pass  # ir.func.exp.ctx |= Ctx.STORE
        else:
            assert False

        if not ir.func_scope():
            assert False
            # we cannot specify the callee because it has not been evaluated yet.
            raise RejectPropagation(ir)

        assert not ir.func_scope().is_class()
        if (self.scope.is_testbench() and
                ir.func_scope().is_function() and not ir.func_scope().is_inlinelib()):
            ir.func_scope().add_tag('function_module')

        if ir.func_scope().is_pure():
            if not env.config.enable_pure:
                fail(self.current_stm, Errors.PURE_IS_DISABLED)
            if not ir.func_scope().parent.is_global():
                fail(self.current_stm, Errors.PURE_MUST_BE_GLOBAL)
            if (ir.func_scope().return_type and
                    not ir.func_scope().return_type.is_undef() and
                    not ir.func_scope().return_type.is_any()):
                return ir.func_scope().return_type
            ret, type_or_error = self.pure_type_inferrer.infer_type(self.current_stm, ir, self.scope)
            if ret:
                return type_or_error
            else:
                fail(self.current_stm, type_or_error)
        elif ir.func_scope().is_method():
            params = ir.func_scope().params[1:]
        else:
            params = ir.func_scope().params[:]
        ir.args = self._normalize_args(ir.func_scope().orig_name, params, ir.args, ir.kwargs)
        if ir.func_scope().is_lib():
            return self.visit_CALL_lib(ir)

        arg_types = [self.visit(arg) for _, arg in ir.args]
        if any([atype.is_undef() for atype in arg_types]):
            assert False
            raise RejectPropagation(ir)
        if ir.func_scope().is_specialized():
            # Must return after ir.args are visited
            return ir.func_scope().return_type
        ret_t = ir.func_scope().return_type
        param_types = [p.sym.typ for p in params]
        if param_types:
            new_param_types = self._get_new_param_types(param_types, arg_types)
            new_scope, is_new = self._specialize_function_with_types(ir.func_scope(), new_param_types)
            if is_new:
                new_scope_sym = ir.func_scope().parent.find_sym(new_scope.orig_name)
                self._add_scope(new_scope)
            else:
                new_scope_sym = ir.func_scope().parent.find_sym(new_scope.orig_name)
            ret_t = new_scope.return_type
            if ir.func.is_a(TEMP):
                ir.func = TEMP(new_scope_sym, Ctx.LOAD)
            elif ir.func.is_a(ATTR):
                ir.func = ATTR(ir.func.exp, new_scope_sym, Ctx.LOAD)
            else:
                assert False
            ir.func.funcall = True
        else:
            self._add_scope(ir.func_scope())
        return ret_t

    def visit_CALL_lib(self, ir):
        if ir.func_scope().orig_name == 'append_worker':
            if not ir.args[0][1].symbol().typ.is_function():
                assert False
            worker = ir.args[0][1].symbol().typ.get_scope()
            if not worker.is_worker():
                worker.add_tag('worker')
            if worker.is_specialized():
                return ir.func_scope().return_type
            arg_types = [self.visit(arg) for _, arg in ir.args[1:]]
            if any([atype.is_undef() for atype in arg_types]):
                raise RejectPropagation(ir)
            if worker.is_method():
                params = worker.params[1:]
            else:
                params = worker.params[:]
            param_types = [p.sym.typ for p in params]
            if param_types:
                new_param_types = self._get_new_param_types(param_types, arg_types)
                new_scope, is_new = self._specialize_worker_with_types(worker, new_param_types)
                if is_new:
                    new_scope_sym = worker.parent.find_sym(new_scope.orig_name)
                    self._add_scope(new_scope)
                else:
                    new_scope_sym = worker.parent.find_sym(new_scope.orig_name)
                if ir.args[0][1].is_a(TEMP):
                    ir.args[0] = (ir.args[0][0], TEMP(new_scope_sym, Ctx.LOAD))
                elif ir.args[0][1].is_a(ATTR):
                    ir.args[0] = (ir.args[0][0], ATTR(ir.args[0][1].exp, new_scope_sym, Ctx.LOAD))
                else:
                    assert False
            else:
                self._add_scope(worker)
        elif ir.func_scope().orig_name == 'assign':
            assert ir.func_scope().parent.is_port()
            _, arg = ir.args[0]
            self.visit(arg)

        assert ir.func_scope().return_type is not None
        assert not ir.func_scope().return_type.is_undef()
        return ir.func_scope().return_type

    def visit_NEW(self, ir):
        ret_t = Type.object(ir.func_scope())
        ir.func_scope().return_type = ret_t
        ctor = ir.func_scope().find_ctor()
        ir.args = self._normalize_args(ir.func_scope().orig_name, ctor.params[1:], ir.args, ir.kwargs)
        arg_types = [self.visit(arg) for _, arg in ir.args]
        if ir.func_scope().is_specialized():
            return ir.func_scope().return_type
        params = ctor.params[1:]
        param_types = [p.sym.typ for p in params]
        if param_types:
            new_param_types = self._get_new_param_types(param_types, arg_types)
            new_scope, is_new = self._specialize_class_with_types(ir.func_scope(), new_param_types)
            if is_new:
                new_ctor = new_scope.find_ctor()
                new_scope_sym = ir.func_scope().parent.gen_sym(new_scope.orig_name)
                new_scope_sym.set_type(Type.klass(new_scope))
                ctor_t = Type.function(new_ctor,
                                       new_scope.return_type,
                                       tuple([new_ctor.params[0].sym.typ] + new_param_types))
                new_ctor_sym = new_scope.find_sym(new_ctor.orig_name)
                new_ctor_sym.set_type(ctor_t)
                self._add_scope(new_scope)
                self._add_scope(new_ctor)
            else:
                new_scope_sym = ir.func_scope().parent.find_sym(new_scope.orig_name)
            ret_t = new_scope.return_type
            ir.sym = new_scope_sym
        else:
            self._add_scope(ir.func_scope())
            self._add_scope(ctor)
        return ret_t

    def _get_new_param_types(self, param_types, arg_types):
        new_param_types = []
        for param_t, arg_t in zip(param_types, arg_types):
            if param_t.is_explicit():
                new_param_t = Type.propagate(param_t, arg_t)
                new_param_types.append(new_param_t)
            else:
                arg_t = arg_t.clone()
                arg_t.set_explicit(False)
                new_param_types.append(arg_t)
        return new_param_types

    def _mangled_names(self, types):
        ts = []
        for t in types:
            if t.is_list():
                elm = self._mangled_names([t.get_element()])
                s = f'l_{elm}'
            elif t.is_tuple():
                elm = self._mangled_names([t.get_element()])
                elms = ''.join([elm] * t.get_length())
                s = f't_{elms}'
            elif t.is_class():
                # TODO: we should avoid naming collision
                s = f'c_{t.get_scope().orig_name}'
            elif t.is_int():
                s = f'i{t.get_width()}'
            elif t.is_bool():
                s = f'b'
            elif t.is_str():
                s = f's'
            elif t.is_object():
                # TODO: we should avoid naming collision
                s = f'o_{t.get_scope().orig_name}'
            else:
                s = str(t)
            ts.append(s)
        return '_'.join(ts)

    def _specialize_function_with_types(self, scope, types):
        assert not scope.is_specialized()
        types = [t.clone() for t in types]
        postfix = self._mangled_names(types)
        assert postfix
        name = f'{scope.orig_name}_{postfix}'
        qualified_name = (scope.parent.name + '.' + name) if scope.parent else name
        if qualified_name in env.scopes:
            return env.scopes[qualified_name], False
        new_scope = scope.instantiate(postfix, scope.children, with_tag=False)
        assert qualified_name == new_scope.name
        assert new_scope.return_type is not None
        if new_scope.is_method():
            params = new_scope.params[1:]
        else:
            params = new_scope.params[:]
        for p, new_t in zip(params, types):
            new_t.set_perfect_explicit()
            p.sym.set_type(new_t)
        new_scope.add_tag('specialized')
        return new_scope, True

    def _specialize_class_with_types(self, scope, types):
        assert not scope.is_specialized()
        if scope.is_port():
            return self._specialize_port_with_types(scope, types)
        types = [t.clone() for t in types]
        postfix = self._mangled_names(types)
        assert postfix
        name = f'{scope.orig_name}_{postfix}'
        qualified_name = (scope.parent.name + '.' + name) if scope.parent else name
        if qualified_name in env.scopes:
            return env.scopes[qualified_name], False

        children = [s for s in scope.children]
        closures = [c for c in scope.collect_scope() if c.is_closure()]
        new_scope = scope.instantiate(postfix, children + closures, with_tag=False)
        assert qualified_name == new_scope.name
        assert new_scope.return_type is not None
        new_scope.return_type = Type.object(new_scope)
        new_ctor = new_scope.find_ctor()
        new_ctor.return_type = Type.object(new_ctor)

        for p, new_t in zip(new_ctor.params[1:], types):
            new_t.set_perfect_explicit()
            p.sym.set_type(new_t)
        new_scope.add_tag('specialized')
        return new_scope, True

    def _specialize_port_with_types(self, scope, types):
        typ = types[0]
        if typ.is_class():
            typscope = typ.get_scope()
            if typscope.is_typeclass():
                dtype = Type.from_typeclass(typscope)
                if typ.has_typeargs():
                    args = typ.get_typeargs()
                    dtype.attrs.update(args)
            else:
                dtype = typ.clone()
        else:
            dtype = typ.clone()
        postfix = self._mangled_names([dtype])
        name = f'{scope.orig_name}_{postfix}'
        qualified_name = (scope.parent.name + '.' + name) if scope.parent else name
        if qualified_name in env.scopes:
            return env.scopes[qualified_name], False
        new_scope = scope.instantiate(postfix, scope.children, with_tag=False)
        assert qualified_name == new_scope.name
        assert new_scope.return_type is not None
        new_scope.return_type = Type.object(new_scope)
        new_ctor = new_scope.find_ctor()
        new_ctor.return_type = Type.object(new_ctor)
        dtype_param = new_ctor.params[1]
        dtype_param.sym.set_type(typ.clone())
        dtype_param.sym.typ.set_explicit(True)
        dtype_param.copy.set_type(typ.clone())
        dtype_param.sym.typ.set_explicit(True)
        init_param = new_ctor.params[3]
        init_param.sym.set_type(dtype.clone())
        init_param.sym.typ.set_explicit(True)
        init_param.copy.set_type(dtype.clone())
        init_param.sym.typ.set_explicit(True)

        new_scope.add_tag('specialized')
        for child in new_scope.children:
            for sym, copy, _ in child.params:
                if sym.typ.is_generic():
                    sym.set_type(dtype.clone())
                    copy.set_type(dtype.clone())
            if child.return_type.is_generic():
                child.return_type = dtype.clone()
            child.add_tag('specialized')
        return new_scope, True

    def _specialize_worker_with_types(self, scope, types):
        assert not scope.is_specialized()
        types = [t.clone() for t in types]
        postfix = self._mangled_names(types)
        assert postfix
        name = f'{scope.orig_name}_{postfix}'
        qualified_name = (scope.parent.name + '.' + name) if scope.parent else name
        if qualified_name in env.scopes:
            return env.scopes[qualified_name], False
        new_scope = scope.instantiate(postfix, scope.children, with_tag=False)
        assert qualified_name == new_scope.name
        assert new_scope.return_type is not None
        if new_scope.is_method():
            params = new_scope.params[1:]
        else:
            params = new_scope.params[:]
        for p, new_t in zip(params, types):
            new_t.set_perfect_explicit()
            p.sym.set_type(new_t)
        new_scope.add_tag('specialized')
        return new_scope, True


class TypeReplacer(IRVisitor):
    def __init__(self, old_t, new_t, comparator):
        self.old_t = old_t
        self.new_t = new_t
        self.comparator = comparator

    def visit_TEMP(self, ir):
        if self.comparator(ir.sym.typ, self.old_t):
            ir.sym.set_type(self.new_t)

    def visit_ATTR(self, ir):
        self.visit(ir.exp)
        if self.comparator(ir.attr.typ, self.old_t):
            ir.attr.set_type(self.new_t)


class InstanceTypePropagation(TypePropagation):
    def _propagate(self, sym, typ):
        if sym.typ.is_object() and sym.typ.get_scope().is_module():
            sym.set_type(typ)


class TypeChecker(IRVisitor):
    def __init__(self):
        super().__init__()

    def visit_UNOP(self, ir):
        return self.visit(ir.exp)

    def visit_BINOP(self, ir):
        l_t = self.visit(ir.left)
        r_t = self.visit(ir.right)
        if ir.op == 'Mult' and l_t.is_seq() and r_t.is_int():
            return l_t

        if not l_t.is_scalar() or not r_t.is_scalar():
            type_error(self.current_stm, Errors.UNSUPPORTED_BINARY_OPERAND_TYPE,
                       [op2sym_map[ir.op], l_t, r_t])
        if l_t.is_bool() and r_t.is_bool() and not ir.op.startswith('Bit'):
            return Type.int(2)
        return l_t

    def visit_RELOP(self, ir):
        l_t = self.visit(ir.left)
        r_t = self.visit(ir.right)
        if not l_t.is_scalar() or not r_t.is_scalar():
            type_error(self.current_stm, Errors.UNSUPPORTED_BINARY_OPERAND_TYPE,
                       [op2sym_map[ir.op], l_t, r_t])
        return Type.bool()

    def visit_CONDOP(self, ir):
        self.visit(ir.cond)
        l_t = self.visit(ir.left)
        r_t = self.visit(ir.right)
        if not Type.is_compatible(l_t, r_t):
            type_error(self.current_stm, Errors.INCOMPTIBLE_TYPES,
                       [l_t, r_t])
        return l_t

    def visit_CALL(self, ir):
        func_sym = ir.func.symbol()
        arg_len = len(ir.args)
        if ir.func_scope().is_lib():
            return ir.func_scope().return_type
        assert ir.func_scope()
        if ir.func_scope().is_pure():
            return Type.any()
        elif ir.func_scope().is_method():
            param_typs = tuple([sym.typ for sym, _, _ in ir.func_scope().params[1:]])
        else:
            param_typs = tuple([sym.typ for sym, _, _ in ir.func_scope().params])
        param_len = len(param_typs)
        with_vararg = param_len and param_typs[-1].has_vararg()
        self._check_param_number(arg_len, param_len, ir, ir.func_scope().orig_name, with_vararg)
        if ir.func_scope().is_specialized():
            scope_name = ir.func_scope().origin.orig_name
        else:
            scope_name = ir.func_scope().orig_name
        self._check_param_type(ir.func_scope(), param_typs, ir, scope_name, with_vararg)

        return ir.func_scope().return_type

    def visit_SYSCALL(self, ir):
        if ir.sym.name == 'len':
            if len(ir.args) != 1:
                type_error(self.current_stm, Errors.LEN_TAKES_ONE_ARG)
            _, mem = ir.args[0]
            if not mem.is_a([TEMP, ATTR]) or not mem.symbol().typ.is_seq():
                type_error(self.current_stm, Errors.LEN_TAKES_SEQ_TYPE)
        elif ir.sym.name == 'print':
            for _, arg in ir.args:
                arg_t = self.visit(arg)
                if not arg_t.is_scalar():
                    type_error(self.current_stm, Errors.PRINT_TAKES_SCALAR_TYPE)
        elif ir.sym.name in env.all_scopes:
            scope = env.all_scopes[ir.sym.name]
            arg_len = len(ir.args)
            param_len = len(scope.params)
            param_typs = tuple([sym.typ for sym, _, _ in scope.params])
            with_vararg = len(param_typs) and param_typs[-1].has_vararg()
            self._check_param_number(arg_len, param_len, ir, ir.sym.name, with_vararg)
            self._check_param_type(scope, param_typs, ir, ir.sym.name, with_vararg)
        else:
            for _, arg in ir.args:
                self.visit(arg)
        assert ir.sym.typ.is_function()
        return ir.sym.typ.get_return_type()

    def visit_NEW(self, ir):
        arg_len = len(ir.args)

        ctor = ir.func_scope().find_ctor()
        if not ctor and arg_len:
            type_error(self.current_stm, Errors.TAKES_TOOMANY_ARGS,
                       [ir.func_scope().orig_name, 0, arg_len])
        param_len = len(ctor.params) - 1
        param_typs = tuple([param.sym.typ for param in ctor.params])[1:]
        with_vararg = len(param_typs) and param_typs[-1].has_vararg()
        self._check_param_number(arg_len, param_len, ir, ir.func_scope().orig_name, with_vararg)
        if ir.func_scope().is_specialized():
            scope_name = ir.func_scope().origin.orig_name
        else:
            scope_name = ir.func_scope().orig_name
        self._check_param_type(ir.func_scope(), param_typs, ir, scope_name, with_vararg)

        return Type.object(ir.func_scope())

    def visit_CONST(self, ir):
        if isinstance(ir.value, bool):
            return Type.bool()
        elif isinstance(ir.value, int):
            return Type.int()
        elif isinstance(ir.value, str):
            return Type.str()
        elif ir.value is None:
            # The value of 'None' is evaluated as int(0)
            return Type.int()
        else:
            type_error(self.current_stm, Errors.UNSUPPORTED_LETERAL_TYPE,
                       [repr(ir)])

    def visit_TEMP(self, ir):
        if (ir.ctx == Ctx.LOAD and
                ir.sym.scope is not self.scope and
                self.scope.has_sym(ir.sym.name) and
                not self.scope.find_sym(ir.sym.name).is_builtin()):
            type_error(self.current_stm, Errors.REFERENCED_BEFORE_ASSIGN,
                       [ir.sym.name])
        return ir.sym.typ

    def visit_ATTR(self, ir):
        return ir.attr.typ

    def visit_MREF(self, ir):
        mem_t = self.visit(ir.mem)
        if mem_t.is_class():
            return mem_t
        assert mem_t.is_seq()
        offs_t = self.visit(ir.offset)
        if not offs_t.is_int():
            type_error(self.current_stm, Errors.MUST_BE_X_TYPE,
                       [ir.offset, 'int', offs_t])
        return mem_t.get_element()

    def visit_MSTORE(self, ir):
        mem_t = self.visit(ir.mem)
        assert mem_t.is_seq()
        offs_t = self.visit(ir.offset)
        if not offs_t.is_int():
            type_error(self.current_stm, Errors.MUST_BE_X_TYPE,
                       [ir.offset, 'int', offs_t])
        exp_t = self.visit(ir.exp)
        elem_t = mem_t.get_element()
        if not Type.is_assignable(elem_t, exp_t):
            type_error(self.current_stm, Errors.INCOMPATIBLE_TYPES,
                       [elem_t, exp_t])
        return mem_t

    def visit_ARRAY(self, ir):
        if self.current_stm.dst.is_a(TEMP) and self.current_stm.dst.symbol().name == '__all__':
            return ir.sym.typ
        for item in ir.items:
            item_type = self.visit(item)
            if not (item_type.is_int() or item_type.is_bool()):
                type_error(self.current_stm, Errors.SEQ_ITEM_MUST_BE_INT,
                           [item_type])
        return ir.sym.typ

    def visit_EXPR(self, ir):
        self.visit(ir.exp)
        if ir.exp.is_a(CALL):
            if ir.exp.func_scope().return_type and ir.exp.func_scope().return_type.is_none():
                #TODO: warning
                pass

    def visit_CJUMP(self, ir):
        self.visit(ir.exp)

    def visit_MCJUMP(self, ir):
        for cond in ir.conds:
            self.visit(cond)

    def visit_JUMP(self, ir):
        pass

    def visit_RET(self, ir):
        exp_t = self.visit(ir.exp)
        if not Type.is_assignable(self.scope.return_type, exp_t):
            type_error(ir, Errors.INCOMPATIBLE_RETURN_TYPE,
                       [self.scope.return_type, exp_t])

    def visit_MOVE(self, ir):
        src_t = self.visit(ir.src)
        dst_t = self.visit(ir.dst)
        if ir.dst.is_a(TEMP) and ir.dst.symbol().is_return():
            assert not dst_t.is_undef()
            if not Type.is_same(dst_t, src_t):
                type_error(ir, Errors.INCOMPATIBLE_RETURN_TYPE,
                           [dst_t, src_t])
        else:
            if not Type.is_assignable(dst_t, src_t):
                type_error(ir, Errors.INCOMPATIBLE_TYPES,
                        [dst_t, src_t])
        if (dst_t.is_seq() and
                dst_t.has_length() and
                isinstance(dst_t.get_length(), int) and
                dst_t.get_length() != Type.ANY_LENGTH):
            if ir.src.is_a(ARRAY):
                if len(ir.src.items * ir.src.repeat.value) > dst_t.get_length():
                    type_error(self.current_stm, Errors.SEQ_CAPACITY_OVERFLOWED,
                               [])

    def visit_PHI(self, ir):
        # FIXME
        #assert ir.var.symbol().typ is not None
        #assert all([arg is None or arg.symbol().typ is not None for arg, blk in ir.args])
        pass

    def _check_param_number(self, arg_len, param_len, ir, scope_name, with_vararg=False):
        if arg_len == param_len:
            pass
        elif arg_len < param_len:
            type_error(self.current_stm, Errors.MISSING_REQUIRED_ARG,
                       [scope_name])
        elif not with_vararg:
            type_error(self.current_stm, Errors.TAKES_TOOMANY_ARGS,
                       [scope_name, param_len, arg_len])

    def _check_param_type(self, scope, param_typs, ir, scope_name, with_vararg=False):
        if with_vararg:
            if len(ir.args) > len(param_typs):
                tails = tuple([param_typs[-1]] * (len(ir.args) - len(param_typs)))
                param_typs = param_typs + tails
        assert len(ir.args) == len(param_typs)
        for (name, arg), param_t in zip(ir.args, param_typs):
            arg_t = self.visit(arg)
            if not Type.is_assignable(param_t, arg_t):
                type_error(self.current_stm, Errors.INCOMPATIBLE_PARAMETER_TYPE,
                           [arg, scope_name])


class PortAssignChecker(IRVisitor):
    def _is_assign_call(self, ir):
        if ir.func_scope().parent.is_port() and ir.func_scope().orig_name == 'assign':
            return True
        elif ir.func_scope().parent.name.startswith('polyphony.Net') and ir.func_scope().orig_name == 'assign':
            return True
        return False

    def visit_CALL(self, ir):
        if self._is_assign_call(ir):
            assert len(ir.args) == 1
            assigned = ir.args[0][1].symbol().typ.get_scope()
            if (not (assigned.is_method() and assigned.parent.is_module()) and
                    not (assigned.parent.is_method() and assigned.parent.parent.is_module())):
                fail(self.current_stm, Errors.PORT_ASSIGN_CANNOT_ACCEPT)
            assigned.add_tag('assigned')
            assigned.add_tag('comb')

    def visit_NEW(self, ir):
        if ir.sym.typ.get_scope().name.startswith('polyphony.Net'):
            if len(ir.args) == 1:
                assigned = ir.args[0][1].symbol().typ.get_scope()
                if (not (assigned.is_method() and assigned.parent.is_module()) and
                        not (assigned.parent.is_method() and assigned.parent.parent.is_module())):
                    fail(self.current_stm, Errors.PORT_ASSIGN_CANNOT_ACCEPT)
                assigned.add_tag('assigned')
                assigned.add_tag('comb')

class EarlyRestrictionChecker(IRVisitor):
    def visit_SYSCALL(self, ir):
        if ir.sym.name in ('range', 'polyphony.unroll', 'polyphony.pipelined'):
            fail(self.current_stm, Errors.USE_OUTSIDE_FOR, [ir.sym.name])


class RestrictionChecker(IRVisitor):
    def visit_NEW(self, ir):
        if ir.func_scope().is_module():
            if not ir.func_scope().parent.is_namespace():
                fail(self.current_stm, Errors.MUDULE_MUST_BE_IN_GLOBAL)
            for i, (_, arg) in enumerate(ir.args):
                if (arg.is_a([TEMP, ATTR])):
                    typ = arg.symbol().typ
                    if typ.is_scalar() or typ.is_class():
                        continue
                    fail(self.current_stm, Errors.MODULE_ARG_MUST_BE_X_TYPE, [typ])
        if self.scope.is_global() and not ir.func_scope().is_module():
            fail(self.current_stm, Errors.GLOBAL_INSTANCE_IS_NOT_SUPPORTED)

    def visit_CALL(self, ir):
        self.visit(ir.func)
        if ir.func_scope().is_method() and ir.func_scope().parent.is_module():
            if ir.func_scope().parent.find_child(self.scope.name, rec=True):
                return
            if ir.func_scope().orig_name == 'append_worker':
                if not (self.scope.is_ctor() and self.scope.parent.is_module()):
                    fail(self.current_stm, Errors.CALL_APPEND_WORKER_IN_CTOR)
                self._check_append_worker(ir)
            if not (self.scope.is_method() and self.scope.parent.is_module()):
                fail(self.current_stm, Errors.CALL_MODULE_METHOD)

    def _check_append_worker(self, call):
        for i, (_, arg) in enumerate(call.args):
            if i == 0:
                func = arg
                assert func.symbol().typ.is_function()
                worker_scope = func.symbol().typ.get_scope()
                if worker_scope.is_method():
                    assert self.scope.is_ctor()
                    if not self.scope.parent.is_subclassof(worker_scope.parent):
                        fail(self.current_stm, Errors.WORKER_MUST_BE_METHOD_OF_MODULE)
                continue
            if arg.is_a(CONST):
                continue
            if (arg.is_a([TEMP, ATTR])):
                typ = arg.symbol().typ
                if typ.is_scalar():
                    continue
                elif typ.is_object():
                    continue
            type_error(self.current_stm, Errors.WORKER_ARG_MUST_BE_X_TYPE,
                       [typ])

    def visit_ATTR(self, ir):
        head = ir.head()
        if (head.scope is not self.scope and
                head.typ.is_object() and
                not self.scope.is_testbench() and
                not self.scope.is_assigned() and
                not self.scope.is_closure()):
            scope = head.typ.get_scope()
            if scope.is_module():
                fail(self.current_stm, Errors.INVALID_MODULE_OBJECT_ACCESS)


class LateRestrictionChecker(IRVisitor):
    def visit_ARRAY(self, ir):
        if not ir.repeat.is_a(CONST):
            fail(self.current_stm, Errors.SEQ_MULTIPLIER_MUST_BE_CONST)

    def visit_MSTORE(self, ir):
        memnode = ir.mem.symbol().typ.get_memnode()
        if memnode.is_alias() and memnode.can_be_reg():
            fail(self.current_stm, Errors.WRITING_ALIAS_REGARRAY)
        if memnode.scope.is_global():
            fail(self.current_stm, Errors.GLOBAL_OBJECT_CANT_BE_MUTABLE)

    def visit_NEW(self, ir):
        if ir.func_scope().is_port():
            if not (self.scope.is_ctor() and self.scope.parent.is_module()):
                fail(self.current_stm, Errors.PORT_MUST_BE_IN_MODULE)

    def visit_MOVE(self, ir):
        super().visit_MOVE(ir)
        reserved_port_name = ('clk', 'rst')
        if ir.src.is_a(NEW) and ir.src.func_scope().is_port():
            if ir.dst.symbol().name in reserved_port_name:
                fail(self.current_stm, Errors.RESERVED_PORT_NAME, [ir.dst.symbol().name])


class AssertionChecker(IRVisitor):
    def visit_SYSCALL(self, ir):
        if ir.sym.name != 'assert':
            return
        _, arg = ir.args[0]
        if arg.is_a(CONST) and not arg.value:
            warn(self.current_stm, Warnings.ASSERTION_FAILED)


class SynthesisParamChecker(object):
    def process(self, scope):
        self.scope = scope
        if scope.synth_params['scheduling'] == 'pipeline':
            if scope.is_worker() or (scope.is_closure() and scope.parent.is_worker()):
                pass
            else:
                fail((env.scope_file_map[scope], scope.lineno),
                     Errors.RULE_FUNCTION_CANNOT_BE_PIPELINED)
        for blk in scope.traverse_blocks():
            if blk.is_loop_head():
                if blk.synth_params['scheduling'] == 'pipeline':
                    loop = scope.find_region(blk)
                    self._check_port_conflict_in_pipeline(loop, scope)

    def _check_port_conflict_in_pipeline(self, loop, scope):
        syms = scope.usedef.get_all_def_syms() | scope.usedef.get_all_use_syms()
        for sym in syms:
            if not sym.typ.is_port():
                continue
            if not sym.typ.get_scope().is_port():
                continue
            usestms = sorted(scope.usedef.get_stms_using(sym), key=lambda s: s.program_order())
            usestms = [stm for stm in usestms if stm.block in loop.blocks()]
            readstms = []
            for stm in usestms:
                if stm.is_a(MOVE) and stm.src.is_a(CALL) and stm.src.func.symbol().orig_name() == 'rd':
                    readstms.append(stm)
            writestms = []
            for stm in usestms:
                if stm.is_a(EXPR) and stm.exp.is_a(CALL) and stm.exp.func.symbol().orig_name() == 'wr':
                    writestms.append(stm)
            if len(readstms) > 1:
                sym = sym.ancestor if sym.ancestor else sym
                fail(readstms[1], Errors.RULE_READING_PIPELINE_IS_CONFLICTED, [sym])
            if len(writestms) > 1:
                sym = sym.ancestor if sym.ancestor else sym
                fail(writestms[1], Errors.RULE_WRITING_PIPELINE_IS_CONFLICTED, [sym])
            if len(readstms) >= 1 and len(writestms) >= 1:
                assert False


class TypeEvalVisitor(IRVisitor):
    def process(self, scope):
        self.type_evaluator = TypeEvaluator(scope)
        for sym, copy, _ in scope.params:
            pt = self._eval(sym.typ)
            sym.set_type(pt)
            pt = self._eval(copy.typ)
            copy.set_type(pt)
        if scope.return_type:
            scope.return_type = self._eval(scope.return_type)
        super().process(scope)

    def _eval(self, typ):
        return self.type_evaluator.visit(typ)

    def visit_TEMP(self, ir):
        ir.sym.typ = self._eval(ir.sym.typ)

    def visit_ATTR(self, ir):
        if not isinstance(ir.attr, str):
            ir.attr.typ = self._eval(ir.attr.typ)

    def visit_SYSCALL(self, ir):
        ir.sym.typ = self._eval(ir.sym.typ)

    def visit_ARRAY(self, ir):
        if ir.sym:
            ir.sym.typ = self._eval(ir.sym.typ)
