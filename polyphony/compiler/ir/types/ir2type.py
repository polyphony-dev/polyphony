from ..ir import *
from ..irvisitor import IRVisitor
from .type import Type

class IR2Type(IRVisitor):
    def to_type(self, ir):
        assert ir.is_a(IRExp)
        t = self.visit(ir)
        if not t:
            t = Type.expr(EXPR(ir))
        return t

    def visit_CONST(self, ir):
        t = None
        if ir.value is None:
            t = Type.none()
        return t

    def visit_TEMP(self, ir):
        t = None
        if ir.symbol.typ.has_scope():
            scope = ir.symbol.typ.scope
            if scope.is_typeclass():
                t = Type.from_typeclass(scope)
            else:
                t = Type.object(scope)
        return t

    def visit_ATTR(self, ir):
        t = None
        if isinstance(ir.symbol, Symbol) and ir.symbol.typ.has_scope():
            scope = ir.symbol.typ.scope
            if scope.is_typeclass():
                t = Type.from_typeclass(scope)
            else:
                t = Type.object(scope)
        return t

    def visit_MREF(self, ir):
        t = None
        if ir.mem.is_a(MREF):
            t = self.to_type(ir.mem, explicit)
            if ir.offset.is_a(CONST):
                t = t.clone(length=ir.offset.value)
            else:
                t = t.clone(length=self.to_type(ir.offset, explicit))
        else:
            t = self.to_type(ir.mem, explicit)
            if t.is_int():  # ir.offset is a width of integer type
                assert ir.offset.is_a(CONST)
                t = t.clone(width=ir.offset.value)
            elif t.is_seq():
                t = t.clone(element=self.to_type(ir.offset, explicit))
            elif t.is_class():
                elm_t = self.to_type(ir.offset, explicit)
                if elm_t.is_object():
                    t = t.clone(scope=elm_t.scope)
                else:
                    type_scope, args = Type.to_scope(elm_t)
                    t = t.clone(scope=type_scope, typeargs=args)
        return t

    def visit_ARRAY(self, ir):
        raise NotImplementedError()


