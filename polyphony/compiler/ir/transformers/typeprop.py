"""Type propagation, specialization, and evaluation using new Ir (ir.py)."""

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import cast
from ..irvisitor import IrVisitor, IrTransformer
from ..ir import (
    Ir,
    IrStm,
    IrExp,
    IrVariable,
    Temp,
    Attr,
    Const,
    Call,
    SysCall,
    New,
    Array,
    MRef,
    MStore,
    Move,
    Expr,
    Phi,
    UPhi,
    LPhi,
    Ret,
    CJump,
    MCJump,
    Jump,
    Ctx,
)
from ..irhelper import qualified_symbols, irexp_type, try_get_constant
from ..scope import Scope
from ..symbol import Symbol
from ..types.type import Type
from ..types.exprtype import ExprType
from ..types.typehelper import type_from_ir, type_from_typeclass, type_to_scope
from ...common.env import env
from ...common.common import fail
from ...common.errors import Errors
from ...frontend.python.pure import PureFuncTypeInferrer
from logging import getLogger

logger = getLogger(__name__)


# ============================================================
# Standalone utility functions
# ============================================================


def normalize_args(func_name, param_names, defvals, args, kwargs):
    """Normalize call arguments: fill in parameter names, defaults, kwargs.

    Unlike _normalize_args, this function does NOT modify kwargs (no side effect).
    """
    nargs = []
    remaining_kwargs = dict(kwargs)
    if len(param_names) < len(args):
        nargs = list(args)
        for name, arg in remaining_kwargs.items():
            nargs.append((name, arg))
        return tuple(nargs)
    for i, (name, defval) in enumerate(zip(param_names, defvals)):
        if i < len(args):
            nargs.append((name, args[i][1]))
        elif name in remaining_kwargs:
            nargs.append((name, remaining_kwargs[name]))
        elif defval:
            nargs.append((name, defval))
        else:
            type_error(None, Errors.MISSING_REQUIRED_ARG_N, [func_name, name])
    return tuple(nargs)


def convert_call(ir, scope):
    """Convert object/port Call to method call (rd/wr/__call__).

    Returns new IrExp via model_copy, or original ir if no conversion needed.
    """
    callee = _get_callee_scope(ir, scope)
    if callee:
        if callee.is_port():
            fun_name = "wr" if ir.args else "rd"
        else:
            fun_name = env.callop_name
        func_sym = callee.find_sym(fun_name)
        if not func_sym:
            fail(None, Errors.IS_NOT_CALLABLE, [callee.name])
        assert func_sym.typ.is_function()
        new_func = Attr(name=fun_name, exp=ir.func, attr=fun_name, ctx=Ctx.LOAD)
        return ir.model_copy(update={'func': new_func, 'name': new_func.name})
    return ir


# ============================================================
# TypeEvaluator & TypeExprEvaluator (moved from typeeval.py)
# ============================================================


class TypeEvaluator(object):
    def __init__(self, scope):
        self.expr_evaluator = TypeExprEvaluator()

    def visit_int(self, t):
        w = self.visit(t.width)
        return t.clone(width=w)

    def visit_bool(self, t):
        return t

    def visit_str(self, t):
        return t

    def visit_list(self, t):
        elm = self.visit(t.element)
        t = t.clone(element=elm)
        if isinstance(t.length, Type):
            assert t.length.is_expr()
            ln = self.visit(t.length)
            if ln.is_expr() and isinstance(ln.expr, Expr) and isinstance(ln.expr.exp, Const):
                t = t.clone(length=ln.expr.exp.value)
            else:
                t = t.clone(length=ln)
        return t

    def visit_tuple(self, t):
        elm = self.visit(t.element)
        t = t.clone(element=elm)
        return t

    def visit_function(self, t):
        from ..scope import FunctionScope

        func = t.scope
        if func and isinstance(func, FunctionScope):
            param_types = []
            for sym in func.param_symbols():
                sym.typ = self.visit(sym.typ)
                param_types.append(sym.typ)
            t = t.clone(param_types=param_types)
            func.return_type = self.visit(func.return_type)
            t = t.clone(return_type=func.return_type)
        else:
            param_types = [self.visit(pt) for pt in t.param_types]
            t = t.clone(param_types=param_types)
            ret_t = self.visit(t.return_type)
            t = t.clone(return_type=ret_t)
        return t

    def visit_object(self, t):
        return t

    def visit_class(self, t):
        return t

    def visit_none(self, t):
        return t

    def visit_undef(self, t):
        return t

    def visit_union(self, t):
        return t

    def visit_expr(self, t):
        result = self.expr_evaluator.visit_expr_type(t)
        if isinstance(result, Type):
            pass
        elif isinstance(result, Expr):
            result = Type.expr(result, t.scope)
        else:
            # Expression node -- wrap in new Ir Expr
            result = Type.expr(Expr(exp=result), t.scope)
        result = result.clone(explicit=t.explicit)
        return result

    def visit(self, t):
        if not isinstance(t, Type):
            return t
        method = "visit_" + t.name
        visitor = getattr(self, method, None)
        if visitor:
            return visitor(t)
        else:
            return None


class TypeExprEvaluator(IrVisitor):
    def visit_expr_type(self, expr_t: ExprType) -> "Type|Ir":
        expr = expr_t.expr
        assert isinstance(expr, Expr)
        self.scope = expr_t.scope
        result = self.visit(expr)
        return result

    def visit_Const(self, ir):
        return ir

    def visit_BinOp(self, ir):
        raise NotImplementedError()

    def sym2type(self, sym):
        sym_t = sym.typ
        if sym_t.is_class():
            typ_scope = sym_t.scope
            if typ_scope.is_typeclass():
                t = type_from_typeclass(typ_scope)
                return t
            elif typ_scope.is_function():
                assert False
            else:
                return Type.object(typ_scope)
        else:
            return None

    def visit_Temp(self, ir):
        sym = self.scope.find_sym(ir.name)
        assert sym
        sym_t = sym.typ
        if sym_t.is_class():
            typ = self.sym2type(sym)
            if typ:
                return typ
        elif sym_t.is_scalar():
            c = try_get_constant((sym,), self.scope)
            if c:
                return c
        return ir

    def visit_Attr(self, ir):
        qsym = qualified_symbols(ir, self.scope)
        sym = qsym[-1]
        assert isinstance(sym, Symbol)
        attr_t = sym.typ
        if attr_t.is_class():
            typ = self.sym2type(sym)
            if typ:
                return typ
        elif attr_t.is_scalar():
            c = try_get_constant(qsym, sym.scope)
            if c:
                return c
        return ir

    def visit_MRef(self, ir):
        expr = self.visit(ir.mem)
        if isinstance(expr, Type):
            expr_typ = expr
            if expr_typ.is_list():
                if expr_typ.element is Type.undef():
                    elm = self.visit(ir.offset)
                    if isinstance(elm, Type):
                        expr_typ = expr_typ.clone(element=elm)
                    else:
                        expr_typ = expr_typ.clone(element=Type.expr(elm))
                elif isinstance(ir.mem, Temp):
                    elm = self.visit(ir.offset)
                    if isinstance(elm, Type):
                        expr_typ = expr_typ.clone(element=elm)
                    else:
                        expr_typ = expr_typ.clone(element=Type.expr(elm))
                else:
                    length = self.visit(ir.offset)
                    if isinstance(length, Const):
                        expr_typ = expr_typ.clone(length=length.value)
                    else:
                        expr_typ = expr_typ.clone(length=Type.expr(length))
            elif expr_typ.is_tuple():
                assert isinstance(ir.mem, Temp)
                elms = self.visit(ir.offset)
                expr_typ = expr_typ.clone(element=elms[0])  # TODO:
                expr_typ = expr_typ.clone(length=len(elms))
            elif expr_typ.is_int():
                width = self.visit(ir.offset)
                if isinstance(width, Const):
                    expr_typ = expr_typ.clone(width=width.value)
            else:
                print(expr_typ)
                assert False
            return expr_typ
        return ir

    def visit_Array(self, ir):
        types = []
        for item in ir.items:
            types.append(self.visit(item))
        if isinstance(types[-1], Const) and types[-1].value is ...:
            # FIXME: tuple should have more than one type
            return types[0]
        if all([isinstance(t, Type) for t in types]):
            # FIXME: tuple should have more than one type
            return types[0]
        return ir

    def visit_Expr(self, ir):
        result = self.visit(ir.exp)
        assert result
        if isinstance(result, Type):
            return result
        else:
            if result is not ir.exp:
                return ir.model_copy(update={'exp': result})
            return ir


def type_error(ir, err_id, args=None):
    fail(ir, err_id, args)


def _get_callee_scope(ir, scope):
    """Resolve callee scope from a Call/New/SysCall node."""
    qsyms = qualified_symbols(ir.func, scope)
    symbol = qsyms[-1]
    assert isinstance(symbol, Symbol)
    func_t = symbol.typ
    assert func_t.has_scope()
    return func_t.scope


class RejectPropagation(Exception):
    pass


# ============================================================
# TypeEvalVisitor (already existed, kept here)
# ============================================================


class TypeEvalVisitor(IrVisitor):
    def process(self, scope):
        self.type_evaluator = TypeEvaluator(scope)
        func = scope.as_function()
        if func:
            for sym in func.param_symbols():
                sym.typ = self._eval(sym.typ)
            if func.return_type:
                func.return_type = self._eval(func.return_type)
        for sym in scope.constants.keys():
            sym.typ = self._eval(sym.typ)
        super().process(scope)

    def _eval(self, typ):
        return self.type_evaluator.visit(typ)

    def visit_Temp(self, ir):
        sym = self.scope.find_sym(ir.name)
        assert sym
        sym.typ = self._eval(sym.typ)

    def visit_Attr(self, ir):
        qsyms = qualified_symbols(ir, self.scope)
        sym = qsyms[-1]
        if not isinstance(sym, str):
            sym.typ = self._eval(sym.typ)


# ============================================================
# TypePropagation
# ============================================================


class TypePropagation(IrVisitor):
    def __init__(self, is_strict=False):
        self.is_strict = is_strict
        self._modified_exp = None

    def _replace_in_block(self, old_stm, new_stm):
        blk = self.scope.find_block(old_stm.block)
        for i, stm in enumerate(blk.stms):
            if stm is old_stm:
                blk.stms[i] = new_stm
                return
        raise ValueError(f"stm not found in block: {old_stm}")

    def process_all(self):
        top = Scope.global_scope()
        target_scopes = [top] + [s for s in top.children if s.is_testbench() and len(s.param_names()) == 0]
        return self.process_scopes(target_scopes)

    def process_scopes(self, scopes):
        self._new_scopes = []
        self._old_scopes = set()
        self._indirect_old_scopes = set()
        self.typed = []
        self.pure_type_inferrer = PureFuncTypeInferrer()
        self.worklist = deque(scopes)
        while self.worklist:
            scope = self.worklist.popleft()
            logger.debug(f"{self.__class__.__name__}.process {scope.name}")
            if scope.is_lib():
                self.typed.append(scope)
                continue
            if scope.is_directory():
                continue
            # Skip scopes that have been replaced by specialized versions
            if scope in self._old_scopes or scope in self._indirect_old_scopes or scope.is_superseded():
                continue
            if scope.is_function() and scope.return_type is None:
                scope.return_type = Type.undef()
            try:
                self.process(scope)
            except RejectPropagation as r:
                logger.debug(r)
                self.worklist.append(scope)
                continue
            logger.debug(f"{scope.name} is typed")
            assert scope not in self.typed
            self.typed.append(scope)
        return self.typed, self._old_scopes

    def process(self, scope):
        """Override IrVisitor.process to iterate block.stms."""
        self.scope = scope
        assert len(scope.entry_block.preds) == 0
        for blk in self.scope.traverse_blocks():
            for stm in blk.stms:
                self.visit(stm)

    def _add_scope(self, scope):
        if scope.is_testbench() and not scope.parent.is_global():
            return
        if (
            scope is not self.scope
            and scope not in self.typed
            and scope not in self.worklist
            and scope not in self._old_scopes
            and scope not in self._indirect_old_scopes
            and not scope.is_superseded()
        ):
            self.worklist.appendleft(scope)
            logger.debug(f"add scope {scope.name}")

    def _find_attr_type_from_specialized(self, scope, attr_name) -> "Type":
        """When a class scope's attribute type is undef,
        look up the type from a specialized version of the scope."""
        parent = scope.parent
        if parent is None:
            return Type.undef()
        base_name = scope.base_name
        for child in parent.children:
            if (
                child is not scope
                and child.is_specialized()
                and child.base_name.startswith(base_name + "_")
                and child.has_sym(attr_name)
            ):
                sym = child.find_sym(attr_name)
                if not sym.typ.is_undef():
                    return sym.typ
        return Type.undef()

    def visit(self, ir) -> Type:
        method = "visit_" + ir.__class__.__name__
        visitor = getattr(self, method, None)
        if isinstance(ir, IrStm):
            self.current_stm = ir
        if visitor:
            if isinstance(ir, IrStm):
                logger.debug(f"---- visit begin {ir}")
                type = visitor(ir)
                logger.debug(f"---- visit end   {ir}")
            else:
                type = visitor(ir)
            return type
        else:
            return None

    def visit_UnOp(self, ir):
        return self.visit(ir.exp)

    def visit_BinOp(self, ir):
        l_t = self.visit(ir.left)
        r_t = self.visit(ir.right)
        if l_t.is_undef() or r_t.is_undef():
            return Type.undef()
        if l_t.is_int() and r_t.is_int():
            w = max(l_t.width, r_t.width)
            if l_t.signed or r_t.signed:
                return Type.int(w, signed=True)
            else:
                return Type.int(w, signed=False)
        return l_t

    def visit_RelOp(self, ir):
        self.visit(ir.left)
        self.visit(ir.right)
        return Type.bool()

    def visit_CondOp(self, ir):
        self.visit(ir.cond)
        ltype = self.visit(ir.left)
        self.visit(ir.right)
        return ltype

    def _convert_call(self, ir):
        clazz = _get_callee_scope(ir, self.scope)
        if clazz:
            if clazz.is_port():
                fun_name = "wr" if ir.args else "rd"
            else:
                fun_name = env.callop_name
            func_sym = clazz.find_sym(fun_name)
            if not func_sym:
                fail(self.current_stm, Errors.IS_NOT_CALLABLE, [clazz.name])
            assert func_sym.typ.is_function()
            new_func = Attr(name=fun_name, exp=ir.func, attr=fun_name, ctx=Ctx.LOAD)
            ir = ir.model_copy(update={'func': new_func, 'name': new_func.name})
        return ir

    def visit_Call(self, ir):
        self.visit(ir.func)
        callee_scope = _get_callee_scope(ir, self.scope)
        param_symbols = callee_scope.param_symbols()
        arg_types = [self.visit(arg) for _, arg in ir.args]
        for sym, arg_t in zip(param_symbols, arg_types):
            self._propagate(sym, arg_t)
        self._add_scope(callee_scope)
        return callee_scope.return_type

    def visit_New(self, ir):
        callee_scope = _get_callee_scope(ir, self.scope)
        ret_t = Type.object(callee_scope)
        ctor = callee_scope.find_ctor()
        param_symbols = ctor.param_symbols()
        arg_types = [self.visit(arg) for _, arg in ir.args]
        for sym, arg_t in zip(param_symbols, arg_types):
            self._propagate(sym, arg_t)
        self._add_scope(callee_scope)
        self._add_scope(ctor)
        return ret_t

    def visit_SysCall(self, ir):
        name = ir.name
        new_args = self._normalize_syscall_args(name, ir.args, ir.kwargs)
        if new_args is not ir.args:
            ir = ir.model_copy(update={'args': new_args})
            self._modified_exp = ir
        for _, arg in ir.args:
            self.visit(arg)
        if name == "polyphony.io.flipped":
            temp = ir.args[0][1]
            temp_t = irexp_type(temp, self.scope)
            if temp_t.is_undef():
                raise RejectPropagation(ir)
            arg_scope = temp_t.scope
            return Type.object(arg_scope)
        elif name == "$new":
            _, arg0 = ir.args[0]
            arg0_t = irexp_type(arg0, self.scope)
            assert arg0_t.is_class()
            self._add_scope(arg0_t.scope)
            return Type.object(arg0_t.scope)
        else:
            sym_t = irexp_type(ir, self.scope)
            assert sym_t.is_function()
            return sym_t.return_type

    def visit_Const(self, ir):
        match ir.value:
            case bool():
                return Type.bool()
            case int():
                return Type.int()
            case str():
                return Type.str()
            case None:
                return Type.int()
            case _:
                type_error(self.current_stm, Errors.UNSUPPORTED_LETERAL_TYPE, [repr(ir)])

    def visit_Temp(self, ir):
        sym = self.scope.find_sym(ir.name)
        assert sym
        sym_t = sym.typ
        if sym_t.is_function() and ir.ctx == Ctx.LOAD:
            func_scope = sym_t.scope
            self._add_scope(func_scope)
        if sym.is_imported():
            self._add_scope(sym.scope)
        return sym.typ

    def visit_Attr(self, ir):
        exptyp = self.visit(ir.exp)
        if exptyp.is_undef():
            raise RejectPropagation(ir)
        if exptyp.is_object() or exptyp.is_class() or exptyp.is_namespace() or exptyp.is_port():
            attr_scope = exptyp.scope
            self._add_scope(attr_scope)
            assert attr_scope.is_containable()

            if not attr_scope.has_sym(ir.name):
                type_error(self.current_stm, Errors.UNKNOWN_ATTRIBUTE, [ir.name])

            symbol = attr_scope.find_sym(ir.name)
            attr_t = symbol.typ
            if attr_t.is_undef() and attr_scope.is_class():
                attr_t = self._find_attr_type_from_specialized(attr_scope, ir.name)
                if not attr_t.is_undef():
                    symbol.typ = attr_t
            exp_sym = qualified_symbols(ir.exp, self.scope)[-1]
            assert isinstance(exp_sym, Symbol)
            assert exptyp == exp_sym.typ
            if attr_t.is_object():
                symbol.add_tag("subobject")
            if exptyp.is_object() and ir.exp.name != env.self_name and self.scope.is_worker():
                exp_sym.add_tag("subobject")
            if attr_t.is_function() and ir.ctx == Ctx.LOAD:
                func_scope = attr_t.scope
                self._add_scope(func_scope)

            return attr_t

        type_error(self.current_stm, Errors.UNKNOWN_ATTRIBUTE, [ir.name])

    def visit_MRef(self, ir):
        mem_t = self.visit(ir.mem)
        if mem_t.is_undef():
            raise RejectPropagation(ir)
        offs_t = self.visit(ir.offset)
        if offs_t.is_undef():
            raise RejectPropagation(ir)

        if mem_t.is_class() and mem_t.scope.is_typeclass():
            t = type_from_ir(self.scope, ir)
            if t.is_object():
                mem_t = mem_t.clone(scope=t.scope)
            else:
                type_scope = type_to_scope(t)
                mem_t = mem_t.clone(scope=type_scope)
            return mem_t
        elif not mem_t.is_seq():
            type_error(self.current_stm, Errors.IS_NOT_SUBSCRIPTABLE, [ir.mem])
        elif mem_t.is_tuple():
            return mem_t.element
        else:
            assert mem_t.is_list()
            if not offs_t.is_int():
                type_error(self.current_stm, Errors.MUST_BE_X_TYPE, [ir.offset, "int", offs_t])
        return mem_t.element

    def visit_MStore(self, ir):
        mem_t = self.visit(ir.mem)
        if mem_t.is_undef():
            raise RejectPropagation(ir)
        mem_sym = qualified_symbols(ir.mem, self.scope)[-1]
        assert isinstance(mem_sym, Symbol)
        mem_sym.typ = mem_t.clone(ro=False)
        offs_t = self.visit(ir.offset)
        if not offs_t.is_int():
            type_error(self.current_stm, Errors.MUST_BE_X_TYPE, [ir.offset, "int", offs_t])
        if not mem_t.is_seq():
            type_error(self.current_stm, Errors.IS_NOT_SUBSCRIPTABLE, [ir.mem])
        return mem_t

    def visit_Array(self, ir):
        if not isinstance(ir.repeat, Const):
            self.visit(ir.repeat)
        item_t = None
        if isinstance(self.current_stm, Move) and isinstance(self.current_stm.dst, IrVariable):
            dst_t = irexp_type(self.current_stm.dst, self.scope)
            if dst_t.is_seq() and dst_t.element.explicit:
                item_t = dst_t.element
        if item_t is None:
            item_typs = [cast(Type, self.visit(item)) for item in ir.items]
            if isinstance(self.current_stm, Move) and self.current_stm.src == ir:
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

        typ = irexp_type(ir, self.scope)
        if typ.is_tuple():
            if isinstance(ir.repeat, Const):
                length = len(ir.items) * ir.repeat.value
            else:
                length = Type.ANY_LENGTH
            typ = typ.clone(element=item_t, length=length)
        else:
            if self.is_strict and isinstance(ir.repeat, Const):
                length = len(ir.items) * ir.repeat.value
            else:
                length = Type.ANY_LENGTH
            typ = typ.clone(element=item_t, length=length)
        return typ

    def visit_Expr(self, ir):
        self._modified_exp = None
        self.visit(ir.exp)
        if self._modified_exp is not None:
            new_ir = ir.model_copy(update={'exp': self._modified_exp})
            self._replace_in_block(ir, new_ir)
            self.current_stm = new_ir
            self._modified_exp = None

    def visit_CJump(self, ir):
        self.visit(ir.exp)

    def visit_MCJump(self, ir):
        for cond in ir.conds:
            self.visit(cond)

    def visit_Jump(self, ir):
        pass

    def visit_Ret(self, ir):
        typ = self.visit(ir.exp)
        self.scope.return_type = typ
        sym = self.scope.parent.find_sym(self.scope.base_name)
        assert isinstance(sym, Symbol)
        sym.typ = sym.typ.clone(return_type=typ)

    def visit_Move(self, ir):
        self._modified_exp = None
        src_typ = self.visit(ir.src)
        if self._modified_exp is not None:
            ir = ir.model_copy(update={'src': self._modified_exp})
            self._replace_in_block(self.current_stm, ir)
            self.current_stm = ir
            self._modified_exp = None
        if src_typ.is_undef():
            raise RejectPropagation(ir)
        dst_typ = self.visit(ir.dst)

        match ir.dst:
            case IrVariable():
                qsyms = qualified_symbols(ir.dst, self.scope)
                symbol = qsyms[-1]
                if not isinstance(symbol, Symbol):
                    raise RejectPropagation(ir)
                self._propagate(symbol, src_typ)
            case Array():
                if src_typ.is_undef():
                    raise RejectPropagation(ir)
                if not src_typ.is_tuple() or not dst_typ.is_tuple():
                    raise RejectPropagation(ir)
                elem_t = src_typ.element
                for item in ir.dst.items:
                    assert isinstance(item, (Temp, Attr, MRef))
                    if isinstance(item, IrVariable):
                        item_qsyms = qualified_symbols(item, self.scope)
                        item_sym = item_qsyms[-1]
                        assert isinstance(item_sym, Symbol)
                        self._propagate(item_sym, elem_t)
                    elif isinstance(item, MRef):
                        mem_qsyms = qualified_symbols(item.mem, self.scope)
                        mem_sym = mem_qsyms[-1]
                        assert isinstance(mem_sym, Symbol)
                        mem_sym.typ = mem_sym.typ.clone(element=elem_t)
            case MRef():
                pass
            case _:
                assert False
        # check mutable method
        if (
            self.scope.is_method()
            and isinstance(ir.dst, Attr)
            and ir.dst.head_name() == env.self_name
            and not self.scope.is_mutable()
        ):
            self.scope.add_tag("mutable")

    def visit_Phi(self, ir):
        qsyms = qualified_symbols(ir.var, self.scope)
        var_sym = qsyms[-1]
        assert isinstance(var_sym, Symbol)
        arg_types = [self.visit(arg) for arg in ir.args]
        for arg_t in arg_types:
            self._propagate(var_sym, arg_t)

    def visit_UPhi(self, ir):
        self.visit_Phi(ir)

    def visit_LPhi(self, ir):
        self.visit_Phi(ir)

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
                type_error(self.current_stm, Errors.MISSING_REQUIRED_ARG_N, [func_name, name])
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
            logger.debug(f"type propagate {sym.name}@{sym.scope.name}: {sym_t} -> {sym.typ}")


# ============================================================
# TypeSpecializer (2-pass wrapper)
# ============================================================


class TypeSpecializer:
    """Type specialization via 2-pass functional architecture.

    Pass 1 (TypeSpecializationAnalyzer): type propagation + scope creation, no IR modification.
    Pass 2 (TypeSpecializerTransformer): IR rewriting using IrTransformer pattern.
    """

    def process_all(self):
        specializer = TypeSpecializationAnalyzer()
        result = specializer.process_all()
        transformer = TypeSpecializerTransformer(result)
        for scope in result.typed_scopes:
            transformer.process(scope)
        return result.typed_scopes, result.old_scopes


# ============================================================
# TypeSpecializationAnalyzer (Pass 1) + TypeSpecializerTransformer (Pass 2)
# ============================================================


@dataclass
class SpecializationResult:
    """Output of TypeSpecializationAnalyzer (Pass 1)."""
    specialization_map: dict = field(default_factory=dict)
    typed_scopes: list = field(default_factory=list)
    old_scopes: set = field(default_factory=set)
    indirect_old_scopes: set = field(default_factory=set)


class TypeSpecializationAnalyzer(TypePropagation):
    """Pass 1: Type propagation + specialization. No IR modification.

    Same type propagation and scope creation logic as TypeSpecializer,
    but does NOT modify IR nodes. Instead, records specialization decisions
    in specialization_map for Pass 2 (TypeSpecializerTransformer) to apply.
    """

    def __init__(self):
        super().__init__(is_strict=False)

    def process_all(self):
        top = Scope.global_scope()
        target_scopes = [top] + [s for s in top.children if s.is_testbench() and len(s.param_names()) == 0]
        return self.process_scopes(target_scopes)

    def process_scopes(self, scopes):
        self._new_scopes = []
        self._old_scopes = set()
        self._indirect_old_scopes = set()
        self.typed = []
        self.pure_type_inferrer = PureFuncTypeInferrer()
        self.specialization_map = {}
        self.worklist = deque(scopes)
        while self.worklist:
            scope = self.worklist.popleft()
            logger.debug(f"{self.__class__.__name__}.process {scope.name}")
            if scope.is_lib():
                self.typed.append(scope)
                continue
            if scope.is_directory():
                continue
            if scope in self._old_scopes or scope in self._indirect_old_scopes or scope.is_superseded():
                continue
            if scope.is_function() and scope.return_type is None:
                scope.return_type = Type.undef()
            try:
                self.process(scope)
            except RejectPropagation as r:
                logger.debug(r)
                self.worklist.append(scope)
                continue
            logger.debug(f"{scope.name} is typed")
            assert scope not in self.typed
            self.typed.append(scope)
        return SpecializationResult(
            specialization_map=dict(self.specialization_map),
            typed_scopes=self.typed,
            old_scopes=self._old_scopes,
            indirect_old_scopes=self._indirect_old_scopes,
        )

    def _resolve_converted_callee(self, ir):
        """Resolve callee scope for object/port calls without modifying IR."""
        callee = _get_callee_scope(ir, self.scope)
        if callee:
            if callee.is_port():
                fun_name = "wr" if ir.args else "rd"
            else:
                fun_name = env.callop_name
            func_sym = callee.find_sym(fun_name)
            if not func_sym:
                fail(self.current_stm, Errors.IS_NOT_CALLABLE, [callee.name])
            assert func_sym.typ.is_function()
            return func_sym.typ.scope
        return None

    def visit_SysCall(self, ir):
        """Override to suppress _modified_exp."""
        name = ir.name
        for _, arg in ir.args:
            self.visit(arg)
        if name == "polyphony.io.flipped":
            temp = ir.args[0][1]
            temp_t = irexp_type(temp, self.scope)
            if temp_t.is_undef():
                raise RejectPropagation(ir)
            arg_scope = temp_t.scope
            return Type.object(arg_scope)
        elif name == "$new":
            _, arg0 = ir.args[0]
            arg0_t = irexp_type(arg0, self.scope)
            assert arg0_t.is_class()
            self._add_scope(arg0_t.scope)
            return Type.object(arg0_t.scope)
        else:
            sym_t = irexp_type(ir, self.scope)
            assert sym_t.is_function()
            return sym_t.return_type

    def visit_Call(self, ir):
        self.visit(ir.func)
        callee_scope = _get_callee_scope(ir, self.scope)
        qsyms = qualified_symbols(ir.func, self.scope)
        func_sym = qsyms[-1]
        assert isinstance(func_sym, Symbol)
        if isinstance(ir.func, Temp):
            func_name = func_sym.orig_name()
            func_t = func_sym.typ
            if func_t.is_object() or func_t.is_port():
                callee_scope = self._resolve_converted_callee(ir)
            elif func_t.is_function():
                assert func_t.has_scope()
            else:
                type_error(self.current_stm, Errors.IS_NOT_CALLABLE, [func_name])
        elif isinstance(ir.func, Attr):
            func_name = func_sym.orig_name()
            func_t = func_sym.typ
            if func_t.is_object() or func_t.is_port():
                callee_scope = self._resolve_converted_callee(ir)
            if func_t.is_undef():
                assert False
                raise RejectPropagation(ir)
            if callee_scope.is_mutable():
                pass
        else:
            assert False

        if not callee_scope:
            assert False
            raise RejectPropagation(ir)

        assert not callee_scope.is_class()
        if (
            self.scope.is_testbench()
            and callee_scope.is_function()
            and not callee_scope.is_inlinelib()
            and callee_scope.parent is not self.scope
        ):
            callee_scope.add_tag("function_module")

        if callee_scope.is_pure():
            if not env.config.enable_pure:
                fail(self.current_stm, Errors.PURE_IS_DISABLED)
            if not callee_scope.parent.is_global():
                fail(self.current_stm, Errors.PURE_MUST_BE_GLOBAL)
            if (
                callee_scope.return_type
                and not callee_scope.return_type.is_undef()
                and not callee_scope.return_type.is_any()
            ):
                return callee_scope.return_type
            ret, type_or_error = self.pure_type_inferrer.infer_type(self.current_stm, ir, self.scope)
            if ret:
                return type_or_error
            else:
                fail(self.current_stm, type_or_error)

        names = callee_scope.param_names()
        defvals = callee_scope.param_default_values()
        normalized_args = normalize_args(callee_scope.base_name, names, defvals, ir.args, ir.kwargs)
        if callee_scope.is_lib():
            return self.visit_Call_lib(ir)

        arg_types = [self.visit(arg) for _, arg in normalized_args]
        if any([atype.is_undef() for atype in arg_types]):
            raise RejectPropagation(ir)
        if callee_scope.is_specialized():
            return callee_scope.return_type
        ret_t = callee_scope.return_type
        param_types = callee_scope.param_types()
        if param_types:
            self._check_param_types(param_types, arg_types, normalized_args, callee_scope.name)
            new_param_types = self._get_new_param_types(param_types, arg_types)
            new_scope, is_new, postfix = self._specialize_function_with_types(callee_scope, new_param_types)
            if callee_scope.is_function_module():
                for t, name in zip(new_param_types, callee_scope.param_names()):
                    if t.is_int() or t.is_bool():
                        continue
                    fail(self.current_stm, Errors.UNSUPPORTED_FUNCTION_MODULE_PARAM_TYPE, [name, t])
            self._new_scopes.append(new_scope)
            owner = self.scope.find_owner_scope(func_sym)
            if owner is not None and owner is not callee_scope.parent:
                self._indirect_old_scopes.add(callee_scope)
                callee_scope.add_tag("superseded")
            else:
                self._old_scopes.add(callee_scope)
            if is_new:
                new_scope_sym = callee_scope.parent.find_sym(new_scope.base_name)
                self._add_scope(new_scope)
            else:
                new_scope_sym = callee_scope.parent.find_sym(new_scope.base_name)
            ret_t = new_scope.return_type
            asname = f"{ir.func.name}_{postfix}"
            if owner and (func_sym.scope is not owner or owner is not callee_scope.parent):
                owner.import_sym(new_scope_sym, asname)
            # Record specialization (NO IR modification)
            self.specialization_map[ir] = (new_scope, postfix)
        else:
            self._add_scope(callee_scope)
        return ret_t

    def visit_New(self, ir):
        callee_scope = _get_callee_scope(ir, self.scope)
        self._add_scope(callee_scope.parent)
        if callee_scope.is_typeclass():
            return type_from_typeclass(callee_scope)
        ret_t = Type.object(callee_scope)
        ctor = callee_scope.find_ctor()
        names = ctor.param_names()
        defvals = ctor.param_default_values()
        normalized_args = normalize_args(callee_scope.base_name, names, defvals, ir.args, ir.kwargs)
        arg_types = [self.visit(arg) for _, arg in normalized_args]
        if callee_scope.is_specialized():
            return callee_scope.find_ctor().return_type
        param_types = ctor.param_types()
        if param_types:
            self._check_param_types(param_types, arg_types, normalized_args, callee_scope.name)
            new_param_types = self._get_new_param_types(param_types, arg_types)
            new_scope, is_new, postfix = self._specialize_class_with_types(callee_scope, new_param_types)
            self._new_scopes.append(new_scope)
            self._old_scopes.add(callee_scope)
            if is_new:
                new_ctor = new_scope.find_ctor()
                new_scope_sym = callee_scope.parent.gen_sym(new_scope.base_name)
                new_scope_sym.typ = Type.klass(new_scope)
                ctor_t = Type.function(
                    new_ctor, Type.object(new_scope), tuple([new_ctor.param_types(with_self=True)[0]] + new_param_types)
                )
                new_ctor_sym = new_scope.find_sym(new_ctor.base_name)
                new_ctor_sym.typ = ctor_t
                self._add_scope(new_scope)
                self._add_scope(new_ctor)
            else:
                new_scope_sym = callee_scope.parent.find_sym(new_scope.base_name)
            ret_t = Type.object(new_scope)
            qsym = qualified_symbols(ir.func, self.scope)
            func_sym = qsym[-1]
            assert isinstance(func_sym, Symbol)
            asname = f"{ir.func.name}_{postfix}"
            owner = self.scope.find_owner_scope(func_sym)
            if owner and func_sym.scope is not owner:
                owner.import_sym(new_scope_sym, asname)
            # Record specialization (NO IR modification)
            self.specialization_map[ir] = (new_scope, postfix)
        else:
            self._add_scope(callee_scope)
            self._add_scope(ctor)
        return ret_t

    def visit_Call_lib(self, ir):
        callee_scope = _get_callee_scope(ir, self.scope)
        if callee_scope.base_name == "append_worker":
            self.visit_Call_append_worker(ir, callee_scope)
        elif callee_scope.base_name == "assign":
            assert callee_scope.parent.is_port()
            _, arg = ir.args[0]
            self.visit(arg)

        assert callee_scope.return_type is not None
        assert not callee_scope.return_type.is_undef()
        return callee_scope.return_type

    def visit_Call_append_worker(self, ir, callee_scope):
        arg_sym = qualified_symbols(ir.args[0][1], self.scope)[-1]
        assert isinstance(arg_sym, Symbol)
        arg_t = arg_sym.typ
        if not arg_t.is_function():
            assert False
        worker = arg_t.scope
        if not worker.is_worker():
            worker.add_tag("worker")
        if worker.is_specialized():
            return callee_scope.return_type
        arg_types = [self.visit(arg) for _, arg in ir.args[1:]]
        if any([atype.is_undef() for atype in arg_types]):
            raise RejectPropagation(ir)
        param_types = worker.param_types()
        if param_types:
            self._check_param_types(param_types, arg_types, ir.args[1:], callee_scope.name)
            new_param_types = self._get_new_param_types(param_types, arg_types)
            new_scope, is_new, postfix = self._specialize_worker_with_types(worker, new_param_types)
            self._new_scopes.append(new_scope)
            self._old_scopes.add(worker)
            if is_new:
                new_scope_sym = worker.parent.find_sym(new_scope.base_name)
                self._add_scope(new_scope)
            else:
                new_scope_sym = worker.parent.find_sym(new_scope.base_name)
            asname = f"{ir.args[0][1].name}_{postfix}"
            if arg_sym.is_imported():
                owner = self.scope.find_owner_scope(arg_sym)
                owner.import_sym(new_scope_sym, asname)
            # Record specialization (NO ir.args mutation)
            # Key is the Call ir containing append_worker
            self.specialization_map[ir] = (new_scope, postfix)
        else:
            self._add_scope(worker)

    # --- Copied from TypeSpecializer (scope operations only, no IR) ---

    def _check_param_types(self, param_types, arg_types, args, scope_name):
        for param_t, arg_t, arg in zip(param_types, arg_types, args):
            if not param_t.explicit:
                continue
            if arg_t.is_expr():
                continue
            if not param_t.can_assign(arg_t):
                arg_var = arg[1]
                if isinstance(arg_var, IrVariable):
                    arg_qsyms = qualified_symbols(arg_var, self.scope)
                    arg_sym = arg_qsyms[-1]
                    if isinstance(arg_sym, Symbol):
                        arg_orig_name = arg_sym.orig_name()
                    else:
                        arg_orig_name = str(arg_var)
                else:
                    arg_orig_name = str(arg_var)
                fail(
                    self.current_stm,
                    Errors.INCOMPATIBLE_FUNCTION_PARAMETER_TYPE,
                    [arg_orig_name, str(arg_t), arg[0], str(param_t), scope_name],
                )

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
        name = f"{scope.base_name}_{postfix}"
        qualified_name = (scope.parent.name + "." + name) if scope.parent else name
        if qualified_name in env.scopes:
            return env.scopes[qualified_name], False, postfix
        new_scope = scope.instantiate(postfix)
        assert qualified_name == new_scope.name
        assert new_scope.return_type is not None
        new_types = []
        for sym, new_t in zip(new_scope.param_symbols(), types):
            sym.typ = new_t.clone(explicit=True)
            new_types.append(new_t)
        new_scope.add_tag("specialized")
        sym = new_scope.parent.find_sym(new_scope.base_name)
        sym.typ = sym.typ.clone(param_types=new_types, return_type=new_scope.return_type)
        return new_scope, True, postfix

    def _specialize_class_with_types(self, scope, types):
        assert not scope.is_specialized()
        if scope.is_port():
            return self._specialize_port_with_types(scope, types)
        postfix = Type.mangled_names(types)
        assert postfix
        name = f"{scope.base_name}_{postfix}"
        qualified_name = (scope.parent.name + "." + name) if scope.parent else name
        if qualified_name in env.scopes:
            return env.scopes[qualified_name], False, postfix
        new_scope = scope.instantiate(postfix)
        assert qualified_name == new_scope.name
        new_ctor = new_scope.find_ctor()
        new_ctor.return_type = Type.object(new_scope)
        for sym, new_t in zip(new_ctor.param_symbols(), types):
            sym.typ = new_t.clone(explicit=True)
        new_scope.add_tag("specialized")
        return new_scope, True, postfix

    def _specialize_port_with_types(self, scope, types):
        typ = types[0]
        if typ.is_class():
            typscope = typ.scope
            if typscope.is_typeclass():
                dtype = type_from_typeclass(typscope)
            else:
                dtype = typ
        else:
            dtype = typ
        postfix = Type.mangled_names([dtype])
        name = f"{scope.base_name}_{postfix}"
        qualified_name = (scope.parent.name + "." + name) if scope.parent else name
        if qualified_name in env.scopes:
            return env.scopes[qualified_name], False, postfix
        new_scope = scope.instantiate(postfix)
        assert qualified_name == new_scope.name
        new_ctor = new_scope.find_ctor()
        new_ctor.return_type = Type.object(new_scope)
        param_symbols = new_ctor.param_symbols()
        dtype_sym = param_symbols[0]
        dtype_sym.typ = typ.clone(explicit=True)
        init_sym = param_symbols[2]
        init_sym.typ = dtype.clone(explicit=True)
        new_scope.add_tag("specialized")
        for child in new_scope.children:
            for sym in child.param_symbols():
                if sym.typ.is_class() and sym.typ.scope.is_object():
                    sym.typ = dtype
            if child.return_type.is_object() and child.return_type.scope.is_object():
                child.return_type = dtype
            child.add_tag("specialized")
        return new_scope, True, postfix

    def _specialize_worker_with_types(self, scope, types):
        assert not scope.is_specialized()
        postfix = Type.mangled_names(types)
        assert postfix
        name = f"{scope.base_name}_{postfix}"
        qualified_name = (scope.parent.name + "." + name) if scope.parent else name
        if qualified_name in env.scopes:
            return env.scopes[qualified_name], False, postfix
        new_scope = scope.instantiate(postfix)
        assert qualified_name == new_scope.name
        assert new_scope.return_type is not None
        param_symbols = new_scope.param_symbols()
        for sym, new_t in zip(param_symbols, types):
            sym.typ = new_t.clone()
        new_scope.add_tag("specialized")
        return new_scope, True, postfix


class TypeSpecializerTransformer(IrTransformer):
    """Pass 2: Rewrite Call/New nodes based on SpecializationResult.

    Uses IrTransformer's functional pattern:
    - IrExp visitors return new/unchanged nodes
    - IrStm visitors collect into new_stms via _process_block
    """

    def __init__(self, result):
        super().__init__()
        self.result = result

    def visit_Call(self, ir):
        # Specialization lookup BEFORE visiting children (ir must match Pass 1 key)
        spec_entry = self.result.specialization_map.get(ir)

        # Visit children (IrTransformer pattern)
        new_func = self.visit(ir.func)
        new_args, args_changed = self._visit_args(ir.args)
        updates = {}
        if new_func is not ir.func:
            updates['func'] = new_func
        if args_changed:
            updates['args'] = new_args

        # Resolve func symbol type
        func_sym = qualified_symbols(ir.func, self.scope)[-1]
        assert isinstance(func_sym, Symbol)
        func_t = func_sym.typ

        # 1. convert_call for object/port types
        if func_t.is_object() or func_t.is_port():
            resolved_ir = ir.model_copy(update=updates) if updates else ir
            resolved_ir = convert_call(resolved_ir, self.scope)
            updates = {}
            ir = resolved_ir

        resolved_ir = ir.model_copy(update=updates) if updates else ir
        callee = _get_callee_scope(resolved_ir, self.scope)

        # 2. normalize_args (before lib check — lib functions also need normalization)
        names = callee.param_names()
        defvals = callee.param_default_values()
        current_args = resolved_ir.args
        new_args = normalize_args(callee.base_name, names, defvals, current_args, resolved_ir.kwargs)
        if new_args is not current_args or resolved_ir.kwargs:
            resolved_ir = resolved_ir.model_copy(update={'args': new_args, 'kwargs': {}})

        # lib functions
        if callee.is_lib():
            if callee.base_name == "append_worker":
                return self._visit_Call_append_worker(resolved_ir, spec_entry)
            return resolved_ir

        # 3. specialization: apply if recorded in Pass 1
        if spec_entry:
            new_scope, postfix = spec_entry
            asname = f"{resolved_ir.func.name}_{postfix}"
            if isinstance(resolved_ir.func, Temp):
                nf = Temp(name=asname, ctx=Ctx.CALL)
            elif isinstance(resolved_ir.func, Attr):
                nf = Attr(
                    name=asname, exp=resolved_ir.func.exp,
                    attr=asname, ctx=resolved_ir.func.ctx,
                )
            else:
                assert False
            resolved_ir = resolved_ir.model_copy(update={'func': nf, 'name': nf.name})

        return resolved_ir

    def visit_New(self, ir):
        # Specialization lookup BEFORE visiting children
        spec_entry = self.result.specialization_map.get(ir)

        new_func = self.visit(ir.func)
        new_args, args_changed = self._visit_args(ir.args)
        updates = {}
        if new_func is not ir.func:
            updates['func'] = new_func
        if args_changed:
            updates['args'] = new_args
        resolved_ir = ir.model_copy(update=updates) if updates else ir

        callee = _get_callee_scope(resolved_ir, self.scope)
        if callee.is_typeclass():
            return resolved_ir

        # normalize_args using ctor params
        ctor = callee.find_ctor()
        current_args = resolved_ir.args
        new_args = normalize_args(
            callee.base_name, ctor.param_names(), ctor.param_default_values(),
            current_args, resolved_ir.kwargs,
        )
        if new_args is not current_args or resolved_ir.kwargs:
            resolved_ir = resolved_ir.model_copy(update={'args': new_args, 'kwargs': {}})

        # specialization: apply if recorded in Pass 1
        if spec_entry:
            new_scope, postfix = spec_entry
            asname = f"{resolved_ir.func.name}_{postfix}"
            if isinstance(resolved_ir.func, Temp):
                nf = Temp(name=asname, ctx=Ctx.CALL)
            elif isinstance(resolved_ir.func, Attr):
                nf = Attr(
                    name=asname, exp=resolved_ir.func.exp,
                    attr=asname, ctx=resolved_ir.func.ctx,
                )
            else:
                assert False
            resolved_ir = resolved_ir.model_copy(update={'func': nf, 'name': nf.name})

        return resolved_ir

    def _visit_Call_append_worker(self, ir, spec_entry):
        """Rewrite worker reference in append_worker call."""
        if not spec_entry:
            return ir
        new_scope, postfix = spec_entry
        worker_exp = ir.args[0][1]
        asname = f"{worker_exp.name}_{postfix}"
        new_args = list(ir.args)
        if isinstance(worker_exp, Temp):
            new_args[0] = (ir.args[0][0], Temp(name=asname))
        elif isinstance(worker_exp, Attr):
            new_scope_sym = new_scope.parent.find_sym(new_scope.base_name)
            new_args[0] = (
                ir.args[0][0],
                Attr(name=new_scope_sym.name, exp=worker_exp.exp,
                     attr=new_scope_sym.name, ctx=worker_exp.ctx),
            )
        return ir.model_copy(update={'args': tuple(new_args)})



# ============================================================
# StaticTypePropagation
# ============================================================


class StaticTypePropagation(TypePropagation):
    def __init__(self, is_strict):
        super().__init__(is_strict=is_strict)

    def process_scopes(self, scopes):
        worklist = deque(scopes)
        while worklist:
            s = worklist.popleft()
            stms = self.collect_stms(s)
            # FIXME: Since lineno is not essential information for Ir,
            #        It should not be used as sort key
            stms = sorted(stms, key=lambda s: s.loc.lineno)
            for stm in stms:
                self.current_stm = stm
                self.scope = s
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

    def visit_Call(self, ir):
        if self.is_strict:
            return super().visit_Call(ir)
        else:
            self.visit(ir.func)
            callee_scope = _get_callee_scope(ir, self.scope)
            return callee_scope.return_type

    def visit_New(self, ir):
        if self.is_strict:
            return super().visit_New(ir)
        else:
            callee_scope = _get_callee_scope(ir, self.scope)
            return Type.object(callee_scope)

    def visit_Attr(self, ir):
        exptyp = self.visit(ir.exp)
        if exptyp.is_undef():
            raise RejectPropagation(ir)
        if exptyp.is_object() or exptyp.is_class() or exptyp.is_namespace() or exptyp.is_port():
            attr_scope = exptyp.scope
            assert attr_scope.is_containable()
            if not attr_scope.has_sym(ir.name):
                type_error(self.current_stm, Errors.UNKNOWN_ATTRIBUTE, [ir.name])
            sym = qualified_symbols(ir, self.scope)[-1]
            assert isinstance(sym, Symbol)
            attr_t = sym.typ
            return attr_t
        type_error(self.current_stm, Errors.UNKNOWN_ATTRIBUTE, [ir.name])


# ============================================================
# TypeReplacer
# ============================================================


class TypeReplacer(IrVisitor):
    def __init__(self, old_t, new_t, comparator):
        self.old_t = old_t
        self.new_t = new_t
        self.comparator = comparator

    def visit_Temp(self, ir):
        sym = self.scope.find_sym(ir.name)
        if sym and self.comparator(sym.typ, self.old_t):
            sym.typ = self.new_t.clone()

    def visit_Attr(self, ir):
        self.visit(ir.exp)
        qsyms = qualified_symbols(ir, self.scope)
        sym = qsyms[-1]
        if isinstance(sym, Symbol) and self.comparator(sym.typ, self.old_t):
            sym.typ = self.new_t.clone()
