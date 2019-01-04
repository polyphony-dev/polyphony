from collections import defaultdict
from .common import fail, warn
from .errors import Errors, Warnings
from .irvisitor import IRVisitor
from .ir import *
from .pure import PureFuncTypeInferrer
from .scope import Scope
from .type import Type
from .env import env
from .symbol import Symbol
import logging
logger = logging.getLogger(__name__)


def type_error(ir, err_id, args=None):
    fail(ir, err_id, args)


class RejectPropagation(Exception):
    pass


class TypePropagation(IRVisitor):
    def __init__(self):
        super().__init__()
        self.check_error = True
        self.new_scopes = set()

    def process_all(self, driver):
        self.check_error = False
        scopes = driver.get_scopes(bottom_up=False,
                                   with_global=True,
                                   with_class=True,
                                   with_lib=False)
        for s in scopes:
            if s.return_type is None:
                s.return_type = Type.undef_t
            else:
                ret = s.symbols[Symbol.return_prefix]
                ret.set_type(s.return_type)
        prev_untyped = []
        while True:
            untyped = []
            for s in scopes:
                self.pure_type_inferrer = PureFuncTypeInferrer()
                try:
                    super().process(s)
                except RejectPropagation as r:
                    #print(r)
                    untyped.append(s)

            if untyped:
                if len(prev_untyped) == len(untyped):
                    # a scope in untyped might be unused,
                    # so we will not make an error cheking here.
                    break
                prev_untyped = untyped[:]
                continue
            break
        for s in scopes:
            self.process(s)
        return [scope for scope in self.new_scopes if not scope.is_lib()]

    def process(self, scope):
        self.pure_type_inferrer = PureFuncTypeInferrer()
        try:
            super().process(scope)
        except RejectPropagation as r:
            pass
        return [scope for scope in self.new_scopes if not scope.is_lib()]

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
        return Type.bool_t

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
            assert func_sym.typ.is_function()
            ir.func = ATTR(ir.func, clazz.symbols[fun_name], Ctx.LOAD)
            ir.func.attr_scope = clazz

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
                if not self.check_error:
                    raise RejectPropagation(ir)
                type_error(self.current_stm, Errors.IS_NOT_CALLABLE,
                           [func_name])
        elif ir.func.is_a(ATTR):
            if not ir.func.attr_scope:
                raise RejectPropagation(ir)
            func_name = ir.func.symbol().orig_name()
            t = ir.func.symbol().typ
            if t.is_object() or t.is_port():
                self._convert_call(ir)
            if t.is_undef():
                raise RejectPropagation(ir)
            if ir.func_scope().is_mutable():
                pass  # ir.func.exp.ctx |= Ctx.STORE
        else:
            assert False

        if not ir.func_scope():
            # we cannot specify the callee because it has not been evaluated yet.
            raise RejectPropagation(ir)

        if ir.func_scope().is_pure():
            if not env.config.enable_pure:
                fail(self.current_stm, Errors.PURE_IS_DISABLED)
            if not ir.func_scope().parent.is_global():
                fail(self.current_stm, Errors.PURE_MUST_BE_GLOBAL)
            if ir.func_scope().return_type and not ir.func_scope().return_type.is_undef() and not ir.func_scope().return_type.is_any():
                return ir.func_scope().return_type
            ret, type_or_error = self.pure_type_inferrer.infer_type(ir, self.scope)
            if ret:
                return type_or_error
            else:
                fail(self.current_stm, type_or_error)
        elif ir.func_scope().is_method():
            params = ir.func_scope().params[1:]
        else:
            params = ir.func_scope().params[:]
        ir.args = self._normalize_args(ir.func_scope().orig_name, params, ir.args, ir.kwargs)
        arg_types = [self.visit(arg) for _, arg in ir.args]
        if any([atype.is_undef() for atype in arg_types]):
            raise RejectPropagation(ir)

        ret_t = ir.func_scope().return_type
        if ir.func_scope().is_class():
            assert False
        else:
            for i, param in enumerate(params):
                if param.sym.typ.is_int() or Type.is_same(param.sym.typ, arg_types[i]):
                    self._set_type(param.sym, arg_types[i].clone())
            funct = Type.function(ir.func_scope(),
                                  ret_t,
                                  tuple([param.sym.typ for param in ir.func_scope().params]))
        self._set_type(ir.func.symbol(), funct)

        if (self.scope.is_testbench() and
                ir.func_scope().is_function() and not ir.func_scope().is_inlinelib()):
            ir.func_scope().add_tag('function_module')

        return ret_t

    def visit_SYSCALL(self, ir):
        ir.args = self._normalize_syscall_args(ir.sym.name, ir.args, ir.kwargs)
        for _, arg in ir.args:
            self.visit(arg)
        assert ir.sym.typ.is_function()
        return ir.sym.typ.get_return_type()

    def visit_NEW(self, ir):
        ret_t = Type.object(ir.func_scope())
        ir.func_scope().return_type = ret_t
        ctor = ir.func_scope().find_ctor()
        ir.args = self._normalize_args(ir.func_scope().orig_name, ctor.params[1:], ir.args, ir.kwargs)
        arg_types = [self.visit(arg) for _, arg in ir.args]
        for i, param in enumerate(ctor.params[1:]):
            if param.sym.typ.is_int() or Type.is_same(param.sym.typ, arg_types[i]):
                self._set_type(param.sym, arg_types[i].clone())
            elif param.sym.typ.is_generic():
                new_scope = self._new_scope_with_type(ir.func_scope(), arg_types[i], i + 1)
                if not new_scope:
                    raise RejectPropagation(ir)
                ir.args.pop(i)
                new_scope_sym = ir.sym.scope.gen_sym(new_scope.orig_name)
                new_scope_sym.set_type(Type.klass(new_scope))
                ir.sym = new_scope_sym
                self.new_scopes.add(new_scope)
                return self.visit_NEW(ir)
        return ret_t

    def visit_CONST(self, ir):
        if isinstance(ir.value, bool):
            return Type.bool_t
        elif isinstance(ir.value, int):
            return Type.int()
        elif isinstance(ir.value, str):
            return Type.str_t
        elif ir.value is None:
            return Type.int()
        else:
            type_error(self.current_stm, Errors.UNSUPPORTED_LETERAL_TYPE,
                       [repr(ir)])

    def visit_TEMP(self, ir):
        if ir.sym.typ.is_undef() and ir.sym.ancestor:
            ir.sym.set_type(ir.sym.ancestor.typ.clone())
        return ir.sym.typ

    def visit_ATTR(self, ir):
        exptyp = self.visit(ir.exp)
        if exptyp.is_object() or exptyp.is_class() or exptyp.is_namespace() or exptyp.is_port():
            attr_scope = exptyp.get_scope()
            ir.attr_scope = attr_scope

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
            return ir.attr.typ

        raise RejectPropagation(ir)

    def visit_MREF(self, ir):
        mem_t = self.visit(ir.mem)
        self.visit(ir.offset)
        if not mem_t.is_seq():
            if self.check_error:
                type_error(self.current_stm, Errors.IS_NOT_SUBSCRIPTABLE,
                           [ir.mem])
            else:
                return Type.undef_t
        return mem_t.get_element()

    def visit_MSTORE(self, ir):
        mem_t = self.visit(ir.mem)
        self.visit(ir.offset)
        if not mem_t.is_seq():
            if self.check_error:
                type_error(self.current_stm, Errors.IS_NOT_SUBSCRIPTABLE,
                           [ir.mem])
            else:
                return Type.undef_t

        exp_t = self.visit(ir.exp)
        elm_t = mem_t.get_element()
        if exp_t.is_scalar() and elm_t.is_scalar():
            if exp_t.get_width() > elm_t.get_width():
                if ir.mem.symbol().typ.is_seq():
                    memnode = ir.mem.symbol().typ.get_memnode()
                else:
                    memnode = None
                self._set_type(ir.mem.symbol(), Type.list(exp_t, memnode))
        return mem_t

    def visit_ARRAY(self, ir):
        if not ir.sym:
            ir.sym = self.scope.add_temp('@array')
        item_t = None
        if self.current_stm.dst.is_a([TEMP, ATTR]):
            dsttyp = self.current_stm.dst.symbol().typ
            if dsttyp.is_seq() and dsttyp.get_element().is_freezed():
                item_t = dsttyp.get_element().clone()
        if item_t is None:
            item_typs = [self.visit(item) for item in ir.items]
            if self.current_stm.src == ir:
                if any([t is Type.undef_t for t in item_typs]):
                    raise RejectPropagation(ir)

            if item_typs and all([Type.is_assignable(item_typs[0], item_t) for item_t in item_typs]):
                if item_typs[0].is_scalar() and not item_typs[0].is_str():
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
            t = Type.tuple(item_t, memnode, len(ir.items))
        self._set_type(ir.sym, t)
        return t

    def _propagate_worker_arg_types(self, call):
        if len(call.args) == 0:
            type_error(self.current_stm, Errors.MISSING_REQUIRED_ARG,
                       [call.func_scope().orig_name])
        _, func = call.args[0]
        if not func.symbol().typ.is_function():
            type_error(self.current_stm, Errors.MUST_BE_X_TYPE,
                       [func.symbol(), 'function', func.symbol().typ])
        worker_scope = func.symbol().typ.get_scope()

        if worker_scope.is_method():
            params = worker_scope.params[1:]
        else:
            params = worker_scope.params[:]

        if len(call.args) > 1:
            _, arg = call.args[1]
            if arg.is_a(ARRAY):
                args = [(None, item) for item in arg.items]
            else:
                args = [(_, arg) for _, arg in call.args[1:]]
        else:
            args = []
        args = self._normalize_args(worker_scope.orig_name, params, args, {})
        arg_types = [self.visit(arg) for _, arg in args]
        for i, param in enumerate(params):
            # we should not set the same type here.
            # because the type of 'sym' and 'copy' might be have different objects(e.g. memnode)
            self._set_type(param.sym, arg_types[i].clone())
            self._set_type(param.copy, arg_types[i].clone())

        funct = Type.function(worker_scope,
                              Type.none_t,
                              tuple([param.sym.typ for param in worker_scope.params]))
        self._set_type(func.symbol(), funct)
        mod_sym = call.func.tail()
        assert mod_sym.typ.is_object()
        if not worker_scope.is_worker():
            worker_scope.add_tag('worker')

    def visit_EXPR(self, ir):
        self.visit(ir.exp)

        if (ir.exp.is_a(CALL) and ir.exp.func_scope().is_method() and
                ir.exp.func_scope().parent.is_module()):
            if ir.exp.func_scope().orig_name == 'append_worker':
                self._propagate_worker_arg_types(ir.exp)

    def visit_CJUMP(self, ir):
        self.visit(ir.exp)

    def visit_MCJUMP(self, ir):
        for cond in ir.conds:
            self.visit(cond)

    def visit_JUMP(self, ir):
        pass

    def visit_RET(self, ir):
        typ = self.visit(ir.exp)
        if self.scope.return_type.is_undef() and not typ.is_undef():
            self.scope.return_type = typ

    def visit_MOVE(self, ir):
        src_typ = self.visit(ir.src)
        if src_typ in (Type.undef_t, Type.generic_t):
            raise RejectPropagation(ir)
        dst_typ = self.visit(ir.dst)

        if ir.dst.is_a([TEMP, ATTR]):
            if not isinstance(ir.dst.symbol(), Symbol):
                # the type of object has not inferenced yet
                raise RejectPropagation(ir)
            self._set_type(ir.dst.symbol(), src_typ.clone())
            if self.scope.is_method() and ir.dst.is_a(ATTR):
                receiver = ir.dst.tail()
                if receiver.typ.is_object():
                    sym = receiver.typ.get_scope().find_sym(ir.dst.symbol().name)
                    self._set_type(sym, src_typ.clone())
        elif ir.dst.is_a(ARRAY):
            if src_typ.is_undef():
                # the type of object has not inferenced yet
                raise RejectPropagation(ir)
            if not src_typ.is_tuple() or not dst_typ.is_tuple():
                raise RejectPropagation(ir)
            elem_t = src_typ.get_element()
            for item in ir.dst.items:
                assert item.is_a([TEMP, ATTR])
                self._set_type(item.symbol(), elem_t.clone())
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
        # TODO: Union type
        for arg_t in arg_types:
            if not arg_t.is_undef() and not ir.var.symbol().typ.is_freezed():
                self._set_type(ir.var.symbol(), arg_t.clone())
                break

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
        return nargs

    def _normalize_syscall_args(self, func_name, args, kwargs):
        return args

    def _set_type(self, sym, typ):
        if not sym.typ.is_freezed():
            sym.set_type(typ)

    def _new_scope_with_type(self, scope, typ, param_idx):
        if typ.is_class():
            typscope = typ.get_scope()
            name = scope.orig_name + '<' + typscope.orig_name + '>'
            if typscope.is_typeclass():
                t = Type.from_typeclass(typscope)
            else:
                t = Type.object(typscope)
        else:
            return None
        qualified_name = (scope.parent.name + '.' + name) if scope.parent else name
        if qualified_name in env.scopes:
            return env.scopes[qualified_name]
        new_scope = scope.inherit(name, scope.children)
        for child in new_scope.children:
            for sym, copy, _ in child.params:
                if Type.is_same(sym.typ, Type.generic_t):
                    sym.set_type(t)
                    copy.set_type(t)
            if Type.is_same(child.return_type, Type.generic_t):
                child.return_type = t
        new_scope.type_args.append(t)
        new_ctor = new_scope.find_ctor()
        new_ctor.params.pop(param_idx)
        return new_scope


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
    def process_all(self):
        scopes = Scope.get_scopes(bottom_up=False, with_global=True)
        for s in scopes:
            self.process(s)

    def _set_type(self, sym, typ):
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
        return Type.bool_t

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
            return Type.any_t
        elif ir.func_scope().is_method():
            param_len = len(ir.func_scope().params) - 1
            param_typs = tuple(func_sym.typ.get_param_types()[1:])
        else:
            param_len = len(ir.func_scope().params)
            param_typs = tuple(func_sym.typ.get_param_types())

        with_vararg = len(param_typs) and param_typs[-1].has_vararg()
        self._check_param_number(arg_len, param_len, ir, ir.func_scope().orig_name, with_vararg)
        self._check_param_type(param_typs, ir, ir.func_scope().orig_name, with_vararg)

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
            self._check_param_type(param_typs, ir, ir.sym.name, with_vararg)
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
        self._check_param_type(param_typs, ir, ir.func_scope().orig_name, with_vararg)

        return Type.object(ir.func_scope())

    def visit_CONST(self, ir):
        if isinstance(ir.value, bool):
            return Type.bool_t
        elif isinstance(ir.value, int):
            return Type.int()
        elif isinstance(ir.value, str):
            return Type.str_t
        elif ir.value is None:
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
            if ir.exp.func_scope().return_type is Type.none_t:
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
            if dst_t is not Type.undef_t and not Type.is_same(src_t, dst_t):
                type_error(ir, Errors.INCOMPATIBLE_RETURN_TYPE,
                           [dst_t, src_t])
        if not Type.is_assignable(dst_t, src_t):
            type_error(ir, Errors.INCOMPATIBLE_TYPES,
                       [dst_t, src_t])
        if (dst_t.is_seq() and dst_t.is_freezed() and
                dst_t.has_length() and
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

    def _check_param_type(self, param_typs, ir, scope_name, with_vararg=False):
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
                not self.scope.is_testbench()):
            scope = head.typ.get_scope()
            if scope.is_module():
                fail(self.current_stm, Errors.INVALID_MODULE_OBJECT_ACCESS)


class LateRestrictionChecker(IRVisitor):
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


class ModuleChecker(IRVisitor):
    def __init__(self):
        super().__init__()
        self.assigns = defaultdict(set)

    def process(self, scope):
        if not (scope.parent and scope.parent.is_module()):
            return
        super().process(scope)

    def visit_MOVE(self, ir):
        if not ir.dst.is_a(ATTR):
            return
        irattr = ir.dst
        if not irattr.exp.is_a(TEMP):
            return
        if irattr.exp.sym.name != env.self_name:
            return
        class_scope = self.scope.parent
        if not self.scope.is_ctor():
            type_error(self.current_stm, Errors.MODULE_FIELD_MUST_ASSIGN_IN_CTOR)

        if irattr.symbol() in self.assigns[class_scope]:
            type_error(self.current_stm, Errors.MODULE_FIELD_MUST_ASSIGN_ONLY_ONCE)

        self.assigns[class_scope].add(irattr.symbol())


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
        if scope.synth_params['scheduling'] == 'pipeline' and not scope.is_worker():
            fail((scope, scope.lineno), Errors.RULE_FUNCTION_CANNOT_BE_PIPELINED)
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
            if sym.typ.get_scope().orig_name.startswith('Port') and sym.typ.get_protocol() == 'none':
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
