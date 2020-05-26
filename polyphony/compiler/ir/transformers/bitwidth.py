from ..irvisitor import IRVisitor
import logging
logger = logging.getLogger(__name__)


class TempVarWidthSetter(IRVisitor):
    def visit_TEMP(self, ir):
        if ir.sym.typ.is_int():
            self.int_types.append(ir.sym.typ)
            # only append an int type temp
            if ir.sym.is_temp():
                self.temps.append(ir.sym)

    def visit_MOVE(self, ir):
        self.temps = []
        self.int_types = []
        super().visit_MOVE(ir)
        if self.temps:
            max_width = max([t.get_width() for t in self.int_types])
            for t in self.temps:
                t.typ = t.typ.with_width(max_width)
