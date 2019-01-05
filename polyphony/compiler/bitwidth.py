from .ahdl import *
from .ahdlvisitor import AHDLVisitor
from .env import env
from .ir import *
from .irvisitor import IRVisitor
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
                t.typ.set_width(max_width)


class BitwidthReducer(AHDLVisitor):
    def process(self, hdlmodule):
        for fsm in hdlmodule.fsms.values():
            self.usedef = fsm.usedef
            for stg in fsm.stgs:
                for state in stg.states:
                    self.visit(state)

    def visit_AHDL_CONST(self, ahdl):
        if isinstance(ahdl.value, int):
            return env.config.default_int_width
        elif isinstance(ahdl.value, str):
            return 1
        elif ir.value is None:
            return 1
        else:
            type_error(self.current_stm, 'unsupported literal type {}'.format(repr(ir)))

    def visit_AHDL_VAR(self, ahdl):
        return ahdl.sig.width

    def visit_AHDL_MEMVAR(self, ahdl):
        return ahdl.sig.width

    def visit_AHDL_SUBSCRIPT(self, ahdl):
        return self.visit(ahdl.memvar)

    def visit_AHDL_OP(self, ahdl):
        if ahdl.is_relop():
            return 1
        widths = [self.visit(a) for a in ahdl.args]

        if ahdl.op == 'BitAnd':
            width = min(widths) + 1  # +1 means signbit for signed destination
        elif ahdl.op == 'Sub':
            width = widths[0]
        elif ahdl.op == 'LShift':
            assert len(ahdl.args) == 2
            width = widths[0] + (1 << widths[1]) - 1
        elif ahdl.op == 'RShift':
            assert len(ahdl.args) == 2
            width = widths[0]
            if ahdl.args[1].is_a(AHDL_CONST) and ahdl.args[0].is_a(AHDL_VAR) and not ahdl.args[0].sig.is_int():
                width -= ahdl.args[1].value
        else:
            width = max(widths)
        if width < 0:
            width = 1
        elif width > env.config.default_int_width:  # TODO
            width = env.config.default_int_width
        return width

    def visit_AHDL_SYMBOL(self, ahdl):
        pass

    def visit_AHDL_CONCAT(self, ahdl):
        return sum([self.visit(var) for var in ahdl.varlist])

    def visit_AHDL_NOP(self, ahdl):
        pass

    def visit_AHDL_MOVE(self, ahdl):
        if ahdl.dst.is_a(AHDL_VAR):
            dst_sig = ahdl.dst.sig
        else:
            return
        if dst_sig.is_output() or dst_sig.is_extport():
            return
        stms = self.usedef.get_stms_defining(dst_sig)
        if len(stms) > 1:
            return
        srcw = self.visit(ahdl.src)
        if srcw is None:
            return
        # TODO:
        #if dst_sig.width > srcw:
        #    dst_sig.width = srcw

    def visit_AHDL_STORE(self, ahdl):
        pass

    def visit_AHDL_LOAD(self, ahdl):
        if ahdl.dst.is_a(AHDL_VAR):
            dst_sig = ahdl.dst.sig
        else:
            return
        if dst_sig.is_output():
            return
        stms = self.usedef.get_stms_defining(dst_sig)
        if len(stms) > 1:
            return
        srcw = self.visit(ahdl.mem)
        if srcw is None:
            return
        if dst_sig.width > srcw:
            dst_sig.width = srcw

    def visit_AHDL_MODULECALL(self, ahdl):
        pass

    def visit_AHDL_FUNCALL(self, ahdl):
        pass

    def visit_AHDL_IF_EXP(self, ahdl):
        lw = self.visit(ahdl.lexp)
        rw = self.visit(ahdl.rexp)
        if lw and rw:
            return lw if lw >= rw else rw
