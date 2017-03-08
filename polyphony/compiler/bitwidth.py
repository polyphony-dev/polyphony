from .ahdl import *
from .ahdlvisitor import AHDLVisitor
from .ir import *
import logging
logger = logging.getLogger(__name__)


class BitwidthReducer(AHDLVisitor):
    def process(self, scope):
        if not scope.module_info:
            return
        self.usedef = scope.ahdlusedef
        #print(self.usedef)
        for fsm in scope.module_info.fsms.values():
            for stg in fsm.stgs:
                for state in stg.states:
                    for code in state.codes:
                        self.visit(code)

    def visit_AHDL_CONST(self, ahdl):
        if isinstance(ahdl.value, int):
            if ahdl.value == 0:
                return 0
            elif ahdl.value > 0:
                return ahdl.value.bit_length()
            else:
                return ahdl.value.bit_length() + 1
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
            if ahdl.args[1].is_a(AHDL_CONST):
                width -= ahdl.args[1].value
        else:
            width = max(widths)
        if width < 0:
            width = 1
        elif width > 64:  # TODO
            width = 64
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
        if dst_sig.width > srcw:
            dst_sig.width = srcw

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
