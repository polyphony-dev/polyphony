from ..irvisitor import IRVisitor
import logging
logger = logging.getLogger(__name__)


class TempVarWidthSetter(IRVisitor):
    def visit_TEMP(self, ir):
        sym = self.scope.find_sym(ir.name)
        assert sym
        if sym.typ.is_int():
            self.int_types.append(sym.typ)
            # only append an int type temp
            if sym.is_temp():
                self.temps.append(sym)

    def visit_MOVE(self, ir):
        self.temps = []
        self.int_types = []
        super().visit_MOVE(ir)
        if self.temps:
            max_width = max([t.width for t in self.int_types])
            for t in self.temps:
                t.typ = t.typ.clone(width=max_width)
