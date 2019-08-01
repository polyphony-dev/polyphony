from .ir import CONST, TEMP
from .irvisitor import IRVisitor
from .type import Type


class TypeEvaluator(object):
    def __init__(self, scope):
        self.expr_evaluator = TypeExprEvaluator(scope)

    def visit_int(self, t):
        w = self.visit(t.get_width())
        t.set_width(w)
        return t

    def visit_bool(self, t):
        return t

    def visit_str(self, t):
        return t

    def visit_list(self, t):
        elm = self.visit(t.get_element())
        t.set_element(elm)
        if isinstance(t.get_length(), Type):
            ln = self.visit(t.get_length())
            if ln.is_expr() and ln.get_expr().is_a(CONST):
                t.set_length(ln.get_expr().value)
            else:
                t.set_length(ln)
        return t

    def visit_tuple(self, t):
        elm = self.visit(t.get_element())
        t.set_element(elm)
        return t

    def visit_function(self, t):
        func = t.get_scope()
        if func:
            param_types = []
            for sym, copy, _ in func.params:
                pt = self.visit(sym.typ)
                sym.set_type(pt)
                copy.set_type(pt.clone())
                param_types.append(pt)
            t.set_param_types(param_types)
            func.return_type = self.visit(func.return_type)
            t.set_return_type(func.return_type)
        else:
            param_types = [self.visit(sym.typ) for pt in t.get_param_types()]
            t.set_param_types(param_types)
            ret_t = self.visit(t.get_return_type())
            t.set_return_type(ret_t)
        return t

    def visit_object(self, t):
        return t

    def visit_class(self, t):
        return t

    def visit_none(self, t):
        return t

    def visit_generic(self, t):
        return t

    def visit_undef(self, t):
        return t

    def visit_expr(self, t):
        result = self.expr_evaluator.visit(t.get_expr())
        if isinstance(result, Type):
            pass
        else:
            result = Type.expr(result)
        result.set_explicit(t.get_explicit())
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
        if sym.typ.is_class():
            typ_scope = sym.typ.get_scope()
            if typ_scope.is_typeclass():
                return Type.from_typeclass(typ_scope)
            elif typ_scope.is_function():
                print(typ_scope.name)
                assert False
            else:
                return Type.object(typ_scope)
        else:
            return None

    def visit_TEMP(self, ir):
        if ir.sym.typ.is_class():
            typ = self.sym2type(ir.sym)
            if typ:
                return typ
        return ir

    def visit_ATTR(self, ir):
        if ir.attr.typ.is_class():
            typ = self.sym2type(ir.attr)
            if typ:
                return typ
        return ir

    def visit_MREF(self, ir):
        expr = self.visit(ir.mem)
        if isinstance(expr, Type):
            expr_typ = expr
            if expr_typ.is_list():
                if expr_typ.get_element() is Type.undef():
                    elm = self.visit(ir.offset)
                    if isinstance(elm, Type):
                        expr_typ.set_element(elm)
                    else:
                        expr_typ.set_element(Type.expr(elm))
                elif ir.mem.is_a(TEMP):
                    elm = self.visit(ir.offset)
                    if isinstance(elm, Type):
                        expr_typ.set_element(elm)
                    else:
                        expr_typ.set_element(Type.expr(elm))
                else:
                    length = self.visit(ir.offset)
                    if length.is_a(CONST):
                        expr_typ.set_length(length.value)
                    else:
                        expr_typ.set_length(Type.expr(length))
            elif expr_typ.is_tuple():
                assert ir.mem.is_a(TEMP)
                elms = self.visit(ir.offset)
                expr_typ.set_element(elms[0])  # TODO:
                expr_typ.set_length(len(elms))
            elif expr_typ.is_int():
                width = self.visit(ir.offset)
                if width.is_a(CONST):
                    expr_typ.set_width(width.value)
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
            return types[0]
        if all([isinstance(t, Type) for t in types]):
            # FIXME:
            return types[0]
        return ir
