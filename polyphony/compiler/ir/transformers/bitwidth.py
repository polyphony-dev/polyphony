from ..irvisitor import IRVisitor
import logging
logger = logging.getLogger(__name__)


class TempVarWidthSetter(IRVisitor):
    def visit_TEMP(self, ir):
        if ir.symbol.typ.is_int():
            self.int_types.append(ir.symbol.typ)
            # only append an int type temp
            if ir.symbol.is_temp():
                self.temps.append(ir.symbol)

    def visit_MOVE(self, ir):
        self.temps = []
        self.int_types = []
        super().visit_MOVE(ir)
        if self.temps:
            max_width = max([t.width for t in self.int_types])
            for t in self.temps:
                t.typ = t.typ.clone(width=max_width)
