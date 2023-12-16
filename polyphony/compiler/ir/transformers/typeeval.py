from .constopt import try_get_constant
from ..ir import CONST, TEMP, EXPR
from ..irhelper import qualified_symbols
from ..irvisitor import IRVisitor
from ..types.type import Type
from ..types.typehelper import type_from_typeclass
from ..symbol import Symbol


class TypeEvaluator(object):
    def __init__(self, scope):
        self.expr_evaluator = TypeExprEvaluator(scope)

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
            if ln.is_expr() and ln.expr.is_a(EXPR) and ln.expr.exp.is_a(CONST):
                t = t.clone(length=ln.expr.exp.value)
            else:
                t = t.clone(length=ln)
        return t

    def visit_tuple(self, t):
        elm = self.visit(t.element)
        t = t.clone(element=elm)
        return t

    def visit_function(self, t):
        func = t.scope
        if func:
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
        result = self.expr_evaluator.visit(t.expr)
        if isinstance(result, Type):
            pass
        else:
            result = Type.expr(result)
        result = result.clone(explicit=t.explicit)
        return result

    def visit(self, t):
        if not isinstance(t, Type):
            return t
        method = 'visit_' + t.name
        visitor = getattr(self, method, None)
        if visitor:
            return visitor(t)
        else:
            return None


class TypeExprEvaluator(IRVisitor):
    def __init__(self, scope):
        self.scope = scope

    def visit_CONST(self, ir):
        return ir

    def visit_BINOP(self, ir):
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

    def visit_TEMP(self, ir):
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

    def visit_ATTR(self, ir):
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

    def visit_MREF(self, ir):
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
                elif ir.mem.is_a(TEMP):
                    elm = self.visit(ir.offset)
                    if isinstance(elm, Type):
                        expr_typ = expr_typ.clone(element=elm)
                    else:
                        expr_typ = expr_typ.clone(element=Type.expr(elm))
                else:
                    length = self.visit(ir.offset)
                    if length.is_a(CONST):
                        expr_typ = expr_typ.clone(length=length.value)
                    else:
                        expr_typ = expr_typ.clone(length=Type.expr(length))
            elif expr_typ.is_tuple():
                assert ir.mem.is_a(TEMP)
                elms = self.visit(ir.offset)
                expr_typ = expr_typ.clone(element=elms[0])  # TODO:
                expr_typ = expr_typ.clone(length=len(elms))
            elif expr_typ.is_int():
                width = self.visit(ir.offset)
                if width.is_a(CONST):
                    expr_typ = expr_typ.clone(width=width.value)
            else:
                print(expr_typ)
                assert False
            return expr_typ
        return ir

    def visit_ARRAY(self, ir):
        types = []
        for item in ir.items:
            types.append(self.visit(item))
        if isinstance(types[-1], CONST) and types[-1].value is ...:
            # FIXME: tuple should have more than one type
            return types[0]
        if all([isinstance(t, Type) for t in types]):
            # FIXME: tuple should have more than one type
            return types[0]
        return ir

    def visit_EXPR(self, ir):
        result = self.visit(ir.exp)
        assert result
        if isinstance(result, Type):
            return result
        else:
            ir.exp = result
            return ir
