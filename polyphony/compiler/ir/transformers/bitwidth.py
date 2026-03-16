"""TempVarWidthSetter using new IR (ir.py)."""
from ..ir_visitor import IrVisitor
import logging
logger = logging.getLogger(__name__)


class NewTempVarWidthSetter(IrVisitor):
    def visit_Temp(self, ir):
        sym = self.scope.find_sym(ir.name)
        assert sym
        if sym.typ.is_int():
            self.int_types.append(sym.typ)
            if sym.is_temp():
                self.temps.append(sym)

    def visit_Move(self, ir):
        self.temps = []
        self.int_types = []
        self.visit(ir.src)
        self.visit(ir.dst)
        if self.temps:
            max_width = max([t.width for t in self.int_types])
            for t in self.temps:
                t.typ = t.typ.clone(width=max_width)
