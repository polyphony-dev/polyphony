from .ahdl import *
from .ahdlvisitor import AHDLVisitor
from .ir import *
from .irvisitor import IRVisitor


class AliasVarDetector(IRVisitor):
    def process(self, scope):
        self.usedef = scope.usedef
        self.removes = []
        super().process(scope)

    def visit_MOVE(self, ir):
        assert ir.dst.is_a([TEMP, ATTR])
        sym = ir.dst.symbol()
        if sym.typ.is_seq() or sym.is_induction() or sym.is_return() or sym.typ.is_port():
            return
        if ir.src.is_a([TEMP, ATTR]):
            src_sym = ir.src.symbol()
            if src_sym.is_param() or src_sym.typ.is_port():
                return
        elif ir.src.is_a(CALL):
            return
        elif ir.src.is_a(MREF):
            memnode = ir.src.mem.symbol().typ.get_memnode()
            if memnode.is_writable():
                return

        stms = self.usedef.get_stms_defining(sym)
        if len(stms) > 1:
            return
        sym.add_tag('alias')


class RegReducer(AHDLVisitor):
    # TODO
    pass