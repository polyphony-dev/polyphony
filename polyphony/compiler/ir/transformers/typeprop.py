﻿from collections import deque
from .typeeval import TypeEvaluator
from ..irvisitor import IRVisitor
from ..ir import *
from ..scope import Scope
from ..types.type import Type
from ..types.typehelper import type_from_ir, type_from_typeclass, type_to_scope
from ..symbol import Symbol
from ...common.env import env
from ...common.common import fail
from ...common.errors import Errors
from ...frontend.python.pure import PureFuncTypeInferrer
import logging
logger = logging.getLogger(__name__)


def type_error(ir, err_id, args=None):
    fail(ir, err_id, args)


class RejectPropagation(Exception):
    pass


class TypePropagation(IRVisitor):
    def __init__(self, is_strict=False):
        # is_strict affects whether type propagation is strict or not
        # In particular, it affects the length of list types. 
        self.is_strict = is_strict

    def process_all(self):
        return self.process_scopes([Scope.global_scope()])

    def process_scopes(self, scopes):
        self._new_scopes = []
        self.typed = []
        self.pure_type_inferrer = PureFuncTypeInferrer()
        self.worklist = deque(scopes)
        while self.worklist:
            scope = self.worklist.popleft()
            logger.debug(f'process {scope.name}')
            # if scope.is_lib():
            #     self.typed.append(scope)
            #     continue
            if scope.is_directory():
                continue
            if scope.is_function() and scope.return_type is None:
                scope.return_type = Type.undef()
            try:
                self.process(scope)
            except RejectPropagation as r:
                logger.debug(r)
                self.worklist.append(scope)
                continue
            logger.debug(f'{scope.name} is typed')
            assert scope not in self.typed
            self.typed.append(scope)
        return self.typed

    def _add_scope(self, scope):
        if scope.is_testbench() and not scope.parent.is_global():
            return
        if scope is not self.scope and scope not in self.typed and scope not in self.worklist:
            self.worklist.append(scope)

    def visit_UNOP(self, ir):
        return self.visit(ir.exp)

    def visit_BINOP(self, ir):
        l_t = self.visit(ir.left)
        r_t = self.visit(ir.right)
        if l_t.is_undef() or r_t.is_undef():
            return Type.undef()
        if l_t.is_int() and r_t.is_int():
            if ir.op in ('Add', 'Sub'):
                w = max(l_t.width, r_t.width) + 1
            elif ir.op == 'Mult':
                w = l_t.width + r_t.width
            else:
                w = l_t.width
            if l_t.signed or r_t.signed:
                return Type.int(w, signed=True)
            else:
                return Type.int(w, signed=False)
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
        clazz = ir.callee_scope
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

    def visit_CALL(self, ir):
        self.visit(ir.func)
        callee_scope = ir.callee_scope
        param_symbols = callee_scope.param_symbols()
        arg_types = [self.visit(arg) for _, arg in ir.args]
        if param_symbols:
            assert callee_scope.is_specialized()
        for sym, arg_t in zip(param_symbols, arg_types):
            self._propagate(sym, arg_t)
        self._add_scope(callee_scope)
        return callee_scope.return_type

    def visit_NEW(self, ir):
        callee_scope = ir.callee_scope
        ret_t = Type.object(callee_scope)
        ctor = callee_scope.find_ctor()
        param_symbols = ctor.param_symbols()
        arg_types = [self.visit(arg) for _, arg in ir.args]
        if param_symbols:
            assert callee_scope.is_specialized()
        for sym, arg_t in zip(param_symbols, arg_types):
            self._propagate(sym, arg_t)
        self._add_scope(callee_scope)
        self._add_scope(ctor)
        return ret_t

    def visit_SYSCALL(self, ir):
        name = ir.symbol.name
        ir.args = self._normalize_syscall_args(name, ir.args, ir.kwargs)
        for _, arg in ir.args:
            self.visit(arg)
        if name == 'polyphony.io.flipped':
            temp = ir.args[0][1]
            temp_t = temp.symbol.typ
            if temp_t.is_undef():
                raise RejectPropagation(ir)
            arg_scope = temp_t.scope
            return Type.object(arg_scope)
        elif name == '$new':
            _, typ = ir.args[0]
            typ_t = typ.symbol.typ
            assert typ_t.is_class()
            return Type.object(typ_t.scope)
        else:
            sym_t = ir.symbol.typ
            assert sym_t.is_function()
            return sym_t.return_type

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
        sym_t = ir.symbol.typ
        if sym_t.is_function() and ir.ctx == Ctx.LOAD:
            # Cases in which a variable of function type is referenced
            func_scope = sym_t.scope
            self._add_scope(func_scope)
        if ir.symbol.is_imported():
            import_src = ir.symbol.import_src()
            self._add_scope(import_src.scope)
        return ir.symbol.typ

    def visit_ATTR(self, ir):
        exptyp = self.visit(ir.exp)
        if exptyp.is_undef():
            raise RejectPropagation(ir)
        if exptyp.is_object() or exptyp.is_class() or exptyp.is_namespace() or exptyp.is_port():
            attr_scope = exptyp.scope
            self._add_scope(attr_scope)
            assert attr_scope.is_containable()
            if isinstance(ir.symbol, str):
                if not attr_scope.has_sym(ir.symbol):
                    type_error(self.current_stm, Errors.UNKNOWN_ATTRIBUTE,
                               [ir.symbol])
                ir.symbol = attr_scope.find_sym(ir.symbol)
            elif attr_scope is not ir.symbol.scope:
                ir.symbol = attr_scope.find_sym(ir.symbol.name)
            assert ir.symbol
            attr_t = ir.symbol.typ
            exp_t = ir.exp.symbol.typ
            if attr_t.is_object():
                ir.symbol.add_tag('subobject')
            if exp_t.is_object() and ir.exp.symbol.name != env.self_name and self.scope.is_worker():
                ir.exp.symbol.add_tag('subobject')
            if attr_t.is_function() and ir.ctx == Ctx.LOAD:
                # Cases in which a variable of function type is referenced
                func_scope = attr_t.scope
                self._add_scope(func_scope)

            return attr_t

        type_error(self.current_stm, Errors.UNKNOWN_ATTRIBUTE, [ir.symbol])

    def visit_MREF(self, ir):
        mem_t = self.visit(ir.mem)
        if mem_t.is_undef():
            raise RejectPropagation(ir)
        offs_t = self.visit(ir.offset)
        if offs_t.is_undef():
            raise RejectPropagation(ir)

        if mem_t.is_class() and mem_t.scope.is_typeclass():
            t = type_from_ir(ir)
            if t.is_object():
                mem_t = mem_t.clone(scope=t.scope)
            else:
                type_scope = type_to_scope(t)
                mem_t = mem_t.clone(scope=type_scope)
            return mem_t
        elif not mem_t.is_seq():
            type_error(self.current_stm, Errors.IS_NOT_SUBSCRIPTABLE,
                       [ir.mem])
        elif mem_t.is_tuple():
            # TODO: Return union type if the offset is variable
            return mem_t.element
        else:
            assert mem_t.is_list()
            if not offs_t.is_int():
                type_error(self.current_stm, Errors.MUST_BE_X_TYPE,
                           [ir.offset, 'int', offs_t])
        return mem_t.element

    def visit_MSTORE(self, ir):
        mem_t = self.visit(ir.mem)
        if mem_t.is_undef():
            raise RejectPropagation(ir)
        ir.mem.symbol.typ = mem_t.clone(ro=False)
        offs_t = self.visit(ir.offset)
        if not offs_t.is_int():
            type_error(self.current_stm, Errors.MUST_BE_X_TYPE,
                       [ir.offset, 'int', offs_t])
        if not mem_t.is_seq():
            type_error(self.current_stm, Errors.IS_NOT_SUBSCRIPTABLE,
                       [ir.mem])
        return mem_t

    def visit_ARRAY(self, ir):
        if not ir.repeat.is_a(CONST):
            self.visit(ir.repeat)
        if not ir.symbol:
            ir.symbol = self.scope.add_temp('@array')
        item_t = None
        if self.current_stm.dst.is_a([TEMP, ATTR]):
            dst_t = self.current_stm.dst.symbol.typ
            if dst_t.is_seq() and dst_t.element.explicit:
                item_t = dst_t.element
        if item_t is None:
            item_typs = [self.visit(item) for item in ir.items]
            if self.current_stm.src == ir:
                if any([t.is_undef() for t in item_typs]):
                    raise RejectPropagation(ir)

            if item_typs and all([item_typs[0].can_assign(item_t) for item_t in item_typs]):
                if item_typs[0].is_scalar() and item_typs[0].is_int():
                    maxwidth = max([item_t.width for item_t in item_typs])
                    signed = any([item_t.is_int() and item_t.signed for item_t in item_typs])
                    item_t = Type.int(maxwidth, signed)
                else:
                    item_t = item_typs[0]
            else:
                assert False  # TODO:

        typ = ir.symbol.typ
        if typ.is_tuple():
            if ir.repeat.is_a(CONST):
                length = len(ir.items) * ir.repeat.value
            else:
                length = Type.ANY_LENGTH
            typ = typ.clone(element=item_t, length=length)
        else:
            if self.is_strict and ir.repeat.is_a(CONST):
                length = len(ir.items) * ir.repeat.value
            else:
                length = Type.ANY_LENGTH
            # readonly = all(item.is_a(CONST) for item in ir.items)
            typ = typ.clone(element=item_t, length=length)
        ir.symbol.typ = typ
        return typ

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
        sym = self.scope.parent.find_sym(self.scope.base_name)
        sym.typ = sym.typ.clone(return_type=typ)

    def visit_MOVE(self, ir):
        src_typ = self.visit(ir.src)
        if src_typ.is_undef():
            raise RejectPropagation(ir)
        dst_typ = self.visit(ir.dst)

        if ir.dst.is_a([TEMP, ATTR]):
            if not isinstance(ir.dst.symbol, Symbol):
                # the type of object has not inferenced yet
                raise RejectPropagation(ir)
            self._propagate(ir.dst.symbol, src_typ)
        elif ir.dst.is_a(ARRAY):
            if src_typ.is_undef():
                # the type of object has not inferenced yet
                raise RejectPropagation(ir)
            if not src_typ.is_tuple() or not dst_typ.is_tuple():
                raise RejectPropagation(ir)
            elem_t = src_typ.element
            for item in ir.dst.items:
                assert item.is_a([TEMP, ATTR, MREF])
                if item.is_a([TEMP, ATTR]):
                    self._propagate(item.symbol, elem_t)
                elif item.is_a(MREF):
                    item.mem.symbol.typ = item.mem.symbol.typ.clone(element=elem_t)
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
            self._propagate(ir.var.symbol, arg_t)

    def visit_UPHI(self, ir):
        self.visit_PHI(ir)

    def visit_LPHI(self, ir):
        self.visit_PHI(ir)

    def _normalize_args(self, func_name, param_names, defvals, args, kwargs):
        nargs = []
        if len(param_names) < len(args):
            nargs = args[:]
            for name, arg in kwargs.items():
                nargs.append((name, arg))
            kwargs.clear()
            return nargs
        for i, (name, defval) in enumerate(zip(param_names, defvals)):
            if i < len(args):
                nargs.append((name, args[i][1]))
            elif name in kwargs:
                nargs.append((name, kwargs[name]))
            elif defval:
                nargs.append((name, defval))
            else:
                type_error(self.current_stm, Errors.MISSING_REQUIRED_ARG_N,
                           [func_name, name])
        kwargs.clear()
        return nargs

    def _normalize_syscall_args(self, func_name, args, kwargs):
        return args

    def _propagate(self, sym, typ):
        sym_t = sym.typ
        if sym_t.is_undef() and typ.is_undef():
            return
        assert not typ.is_undef()
        sym.typ = sym_t.propagate(typ)
        if sym.typ != sym_t:
            logger.debug(f'type propagate {sym.name}: {sym_t} -> {sym.typ}')


class TypeSpecializer(TypePropagation):
    def __init__(self):
        super().__init__(is_strict=False)

    def visit_CALL(self, ir):
        self.visit(ir.func)
        callee_scope = ir.callee_scope
        if ir.func.is_a(TEMP):
            func_name = ir.symbol.orig_name()
            func_t = ir.symbol.typ
            if func_t.is_object() or func_t.is_port():
                self._convert_call(ir)
                callee_scope = ir.callee_scope
            elif func_t.is_function():
                assert func_t.has_scope()
            else:
                type_error(self.current_stm, Errors.IS_NOT_CALLABLE,
                           [func_name])
        elif ir.func.is_a(ATTR):
            func_name = ir.symbol.orig_name()
            func_t = ir.symbol.typ
            if func_t.is_object() or func_t.is_port():
                self._convert_call(ir)
            if func_t.is_undef():
                assert False
                raise RejectPropagation(ir)
            if callee_scope.is_mutable():
                pass  # ir.func.exp.ctx |= Ctx.STORE
        else:
            assert False

        if not callee_scope:
            assert False
            # we cannot specify the callee because it has not been evaluated yet.
            raise RejectPropagation(ir)

        assert not callee_scope.is_class()
        if (self.scope.is_testbench() and
                callee_scope.is_function() and not callee_scope.is_inlinelib()):
            callee_scope.add_tag('function_module')

        if callee_scope.is_pure():
            if not env.config.enable_pure:
                fail(self.current_stm, Errors.PURE_IS_DISABLED)
            if not callee_scope.parent.is_global():
                fail(self.current_stm, Errors.PURE_MUST_BE_GLOBAL)
            if (callee_scope.return_type and
                    not callee_scope.return_type.is_undef() and
                    not callee_scope.return_type.is_any()):
                return callee_scope.return_type
            ret, type_or_error = self.pure_type_inferrer.infer_type(self.current_stm, ir, self.scope)
            if ret:
                return type_or_error
            else:
                fail(self.current_stm, type_or_error)
        names = callee_scope.param_names()
        defvals = callee_scope.param_default_values()
        ir.args = self._normalize_args(callee_scope.base_name, names, defvals, ir.args, ir.kwargs)
        if callee_scope.is_lib():
            return self.visit_CALL_lib(ir)

        arg_types = [self.visit(arg) for _, arg in ir.args]
        if any([atype.is_undef() for atype in arg_types]):
            assert False
            raise RejectPropagation(ir)
        if callee_scope.is_specialized():
            # Must return after ir.args are visited
            return callee_scope.return_type
        ret_t = callee_scope.return_type
        param_types = callee_scope.param_types()
        if param_types:
            self._check_param_types(param_types, arg_types, ir.args, callee_scope.name)
            new_param_types = self._get_new_param_types(param_types, arg_types)
            new_scope, is_new = self._specialize_function_with_types(callee_scope, new_param_types)
            self._new_scopes.append(new_scope)
            if is_new:
                new_scope_sym = callee_scope.parent.find_sym(new_scope.base_name)
                self._add_scope(new_scope)
            else:
                new_scope_sym = callee_scope.parent.find_sym(new_scope.base_name)
            ret_t = new_scope.return_type
            if ir.func.is_a(TEMP):
                ir.func = TEMP(new_scope_sym, Ctx.LOAD)
            elif ir.func.is_a(ATTR):
                ir.func = ATTR(ir.func.exp, new_scope_sym, Ctx.LOAD)
            else:
                assert False
        else:
            self._add_scope(callee_scope)
        return ret_t

    def visit_CALL_lib(self, ir):
        callee_scope = ir.callee_scope
        if callee_scope.base_name == 'append_worker':
            arg_t = ir.args[0][1].symbol.typ
            if not arg_t.is_function():
                assert False
            worker = arg_t.scope
            if not worker.is_worker():
                worker.add_tag('worker')
            if worker.is_specialized():
                return callee_scope.return_type
            arg_types = [self.visit(arg) for _, arg in ir.args[1:]]
            if any([atype.is_undef() for atype in arg_types]):
                raise RejectPropagation(ir)
            param_types = worker.param_types()
            if param_types:
                self._check_param_types(param_types, arg_types, ir.args[1:], callee_scope.name)
                new_param_types = self._get_new_param_types(param_types, arg_types)
                new_scope, is_new = self._specialize_worker_with_types(worker, new_param_types)
                self._new_scopes.append(new_scope)
                if is_new:
                    new_scope_sym = worker.parent.find_sym(new_scope.base_name)
                    self._add_scope(new_scope)
                else:
                    new_scope_sym = worker.parent.find_sym(new_scope.base_name)
                if ir.args[0][1].is_a(TEMP):
                    ir.args[0] = (ir.args[0][0], TEMP(new_scope_sym, Ctx.LOAD))
                elif ir.args[0][1].is_a(ATTR):
                    ir.args[0] = (ir.args[0][0], ATTR(ir.args[0][1].exp, new_scope_sym, Ctx.LOAD))
                else:
                    assert False
            else:
                self._add_scope(worker)
        elif callee_scope.base_name == 'assign':
            assert callee_scope.parent.is_port()
            _, arg = ir.args[0]
            self.visit(arg)

        assert callee_scope.return_type is not None
        assert not callee_scope.return_type.is_undef()
        return callee_scope.return_type

    def visit_NEW(self, ir):
        callee_scope = ir.callee_scope
        self._add_scope(callee_scope.parent)
        if callee_scope.is_typeclass():
            return type_from_typeclass(callee_scope)
        ret_t = Type.object(callee_scope)
        ctor = callee_scope.find_ctor()
        names = ctor.param_names()
        defvals = ctor.param_default_values()
        ir.args = self._normalize_args(callee_scope.base_name, names, defvals, ir.args, ir.kwargs)
        arg_types = [self.visit(arg) for _, arg in ir.args]
        if callee_scope.is_specialized():
            return callee_scope.find_ctor().return_type
        param_types = ctor.param_types()
        if param_types:
            self._check_param_types(param_types, arg_types, ir.args, callee_scope.name)
            new_param_types = self._get_new_param_types(param_types, arg_types)
            new_scope, is_new = self._specialize_class_with_types(callee_scope, new_param_types)
            self._new_scopes.append(new_scope)
            if is_new:
                new_ctor = new_scope.find_ctor()
                new_scope_sym = callee_scope.parent.gen_sym(new_scope.base_name)
                new_scope_sym.typ = Type.klass(new_scope)
                ctor_t = Type.function(new_ctor,
                                       Type.object(new_scope),
                                       tuple([new_ctor.param_types(with_self=True)[0]] + new_param_types))
                new_ctor_sym = new_scope.find_sym(new_ctor.base_name)
                new_ctor_sym.typ = ctor_t
                self._add_scope(new_scope)
                self._add_scope(new_ctor)
            else:
                new_scope_sym = callee_scope.parent.find_sym(new_scope.base_name)
            ret_t = Type.object(new_scope)
            if ir.symbol.scope is not new_scope_sym.scope:
                ir.symbol.scope.import_sym(new_scope_sym)
            ir.symbol = new_scope_sym
        else:
            self._add_scope(callee_scope)
            self._add_scope(ctor)
        return ret_t

    def _check_param_types(self, param_types, arg_types, args, scope_name):
        for param_t, arg_t, arg in zip(param_types, arg_types, args):
            if not param_t.explicit:
                continue
            # Since eval_type is performed later, the expr type is not checked here
            if arg_t.is_expr():
                continue
            if not param_t.can_assign(arg_t):
                fail(self.current_stm, Errors.INCOMPATIBLE_FUNCTION_PARAMETER_TYPE,
                     [arg[1].symbol.orig_name(),
                      str(arg_t),
                      arg[0],
                      str(param_t),
                      scope_name])

    def _get_new_param_types(self, param_types, arg_types):
        new_param_types = []
        for param_t, arg_t in zip(param_types, arg_types):
            if param_t.explicit:
                new_param_t = param_t.propagate(arg_t)
                new_param_types.append(new_param_t)
            else:
                arg_t = arg_t.clone(explicit=False)
                new_param_types.append(arg_t)
        return new_param_types

    def _specialize_function_with_types(self, scope, types):
        assert not scope.is_specialized()
        postfix = Type.mangled_names(types)
        assert postfix
        name = f'{scope.base_name}_{postfix}'
        qualified_name = (scope.parent.name + '.' + name) if scope.parent else name
        if qualified_name in env.scopes:
            return env.scopes[qualified_name], False
        new_scope = scope.instantiate(postfix, scope.children, with_tag=False)
        assert qualified_name == new_scope.name
        assert new_scope.return_type is not None
        new_types = []
        for sym, new_t in zip(new_scope.param_symbols(), types):
            sym.typ = new_t.clone(explicit=True)
            new_types.append(new_t)
        new_scope.add_tag('specialized')
        sym = new_scope.parent.find_sym(new_scope.base_name)
        sym.typ = sym.typ.clone(param_types=new_types, return_type=new_scope.return_type)
        return new_scope, True

    def _specialize_class_with_types(self, scope, types):
        assert not scope.is_specialized()
        if scope.is_port():
            return self._specialize_port_with_types(scope, types)
        postfix = Type.mangled_names(types)
        assert postfix
        name = f'{scope.base_name}_{postfix}'
        qualified_name = (scope.parent.name + '.' + name) if scope.parent else name
        if qualified_name in env.scopes:
            return env.scopes[qualified_name], False

        children = [s for s in scope.children]
        closures = [c for c in scope.collect_scope() if c.is_closure()]
        new_scope = scope.instantiate(postfix, children + closures, with_tag=False)
        assert qualified_name == new_scope.name
        new_ctor = new_scope.find_ctor()
        new_ctor.return_type = Type.object(new_scope)

        for sym, new_t in zip(new_ctor.param_symbols(), types):
            sym.typ = new_t.clone(explicit=True)
        new_scope.add_tag('specialized')
        return new_scope, True

    def _specialize_port_with_types(self, scope, types):
        typ = types[0]
        if typ.is_class():
            typscope = typ.scope
            if typscope.is_typeclass():
                dtype = type_from_typeclass(typscope)
                #if typ.has_typeargs():
                #    args = typ.get_typeargs()
                #    dtype.attrs.update(args)  # FIXME
            else:
                dtype = typ
        else:
            dtype = typ
        postfix = Type.mangled_names([dtype])
        name = f'{scope.base_name}_{postfix}'
        qualified_name = (scope.parent.name + '.' + name) if scope.parent else name
        if qualified_name in env.scopes:
            return env.scopes[qualified_name], False
        new_scope = scope.instantiate(postfix, scope.children, with_tag=False)
        assert qualified_name == new_scope.name
        new_ctor = new_scope.find_ctor()
        new_ctor.return_type = Type.object(new_scope)
        param_symbols = new_ctor.param_symbols()
        dtype_sym = param_symbols[0]
        dtype_sym.typ = typ.clone(explicit=True)
        init_sym = param_symbols[2]
        init_sym.typ = dtype.clone(explicit=True)

        new_scope.add_tag('specialized')
        for child in new_scope.children:
            for sym in child.param_symbols():
                if sym.typ.is_class() and sym.typ.scope.is_object():
                    sym.typ = dtype
            if child.return_type.is_object() and child.return_type.scope.is_object():
                child.return_type = dtype
            child.add_tag('specialized')
        return new_scope, True

    def _specialize_worker_with_types(self, scope, types):
        assert not scope.is_specialized()
        postfix = Type.mangled_names(types)
        assert postfix
        name = f'{scope.base_name}_{postfix}'
        qualified_name = (scope.parent.name + '.' + name) if scope.parent else name
        if qualified_name in env.scopes:
            return env.scopes[qualified_name], False
        new_scope = scope.instantiate(postfix, scope.children, with_tag=False)
        assert qualified_name == new_scope.name
        assert new_scope.return_type is not None
        param_symbols = new_scope.param_symbols()
        for sym, new_t in zip(param_symbols, types):
            sym.typ = new_t.clone()
        new_scope.add_tag('specialized')
        return new_scope, True


class DynamicTypePropagation(TypePropagation):
    def __init__(self, is_strict):
        super().__init__(is_strict=is_strict)


class StaticTypePropagation(TypePropagation):
    def __init__(self, is_strict):
        super().__init__(is_strict=is_strict)

    def process_scopes(self, scopes):
        stms = []
        #dtrees = {}
        worklist = deque(scopes)
        while worklist:
            s = worklist.popleft()
            stms = self.collect_stms(s)
            # FIXME: Since lineno is not essential information for IR,
            #        It should not be used as sort key
            stms = sorted(stms, key=lambda s: s.loc.lineno)
            for stm in stms:
                self.current_stm = stm
                self.scope = stm.block.scope
                try:
                    self.visit(stm)
                except RejectPropagation as r:
                    worklist.append(s)
                    break

    def collect_stms(self, scope):
        stms = []
        for blk in scope.traverse_blocks():
            stms.extend(blk.stms)
        return stms

    def _add_scope(self, scope):
        pass

    def visit_CALL(self, ir):
        if self.is_strict:
            return super().visit_CALL(ir)
        else:
            self.visit(ir.func)
            return ir.callee_scope.return_type

    def visit_NEW(self, ir):
        if self.is_strict:
            return super().visit_NEW(ir)
        else:
            return Type.object(ir.callee_scope)

    def visit_ATTR(self, ir):
        exptyp = self.visit(ir.exp)
        if exptyp.is_undef():
            raise RejectPropagation(ir)
        if exptyp.is_object() or exptyp.is_class() or exptyp.is_namespace() or exptyp.is_port():
            attr_scope = exptyp.scope
            assert attr_scope.is_containable()
            if isinstance(ir.symbol, str):
                if not attr_scope.has_sym(ir.symbol):
                    type_error(self.current_stm, Errors.UNKNOWN_ATTRIBUTE,
                               [ir.symbol])
                ir.symbol = attr_scope.find_sym(ir.symbol)
            assert ir.symbol
            attr_t = ir.symbol.typ
            return attr_t

        type_error(self.current_stm, Errors.UNKNOWN_ATTRIBUTE, [ir.symbol])


class TypeReplacer(IRVisitor):
    def __init__(self, old_t, new_t, comparator):
        self.old_t = old_t
        self.new_t = new_t
        self.comparator = comparator

    def visit_TEMP(self, ir):
        if self.comparator(ir.symbol.typ, self.old_t):
            ir.symbol.typ = self.new_t.clone()

    def visit_ATTR(self, ir):
        self.visit(ir.exp)
        if self.comparator(ir.symbol.typ, self.old_t):
            ir.symbol.typ = self.new_t.clone()


class TypeEvalVisitor(IRVisitor):
    def process(self, scope):
        self.type_evaluator = TypeEvaluator(scope)
        for sym in scope.param_symbols():
            sym.typ = self._eval(sym.typ)
        if scope.return_type:
            scope.return_type = self._eval(scope.return_type)
        for sym in scope.constants.keys():
            sym.typ = self._eval(sym.typ)
        super().process(scope)

    def _eval(self, typ):
        return self.type_evaluator.visit(typ)

    def visit_TEMP(self, ir):
        ir.symbol.typ = self._eval(ir.symbol.typ)

    def visit_ATTR(self, ir):
        if not isinstance(ir.symbol, str):
            ir.symbol.typ = self._eval(ir.symbol.typ)

    def visit_SYSCALL(self, ir):
        ir.symbol.typ = self._eval(ir.symbol.typ)

    def visit_ARRAY(self, ir):
        if ir.symbol:
            ir.symbol.typ = self._eval(ir.symbol.typ)
