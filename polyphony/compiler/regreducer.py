from .ahdl import *
from .ahdlvisitor import AHDLVisitor

class RegReducer(AHDLVisitor):
    def process(self, scope):
        if not scope.module_info:
            return
        self.module_info = scope.module_info
        self.usedef = scope.ahdlusedef
        self.removes = []
        for fsm in scope.module_info.fsms.values():
            for stg in fsm.stgs:
                for state in stg.states:
                    self.visit_codes(state.codes)

    def visit_codes(self, codes):
        removes = self.removes[:]
        self.removes = []
        for code in codes:
            self.visit(code)
        for mv in self.removes:
            assert mv.is_a(AHDL_MOVE)
            self.module_info.add_static_assignment(AHDL_ASSIGN(mv.dst, mv.src))
            idx = codes.index(mv)
            codes.remove(mv)
            #codes.insert(idx, AHDL_NOP(str(mv)))
        self.removes = removes

    def visit_AHDL_MOVE(self, ahdl):
        if ahdl.dst.is_a(AHDL_VAR) or ahdl.dst.is_a(AHDL_MEMVAR):
            dst_sig = ahdl.dst.sig
        elif ahdl.dst.is_a(AHDL_SUBSCRIPT):
            dst_sig = ahdl.dst.memvar.sig
        else:
            assert False
        if dst_sig.is_output() or dst_sig.is_extport():
            return
        if ahdl.src.is_a(AHDL_VAR):
           if ahdl.src.sig.is_input() or ahdl.src.sig.is_extport():
                return
        if ahdl.src.is_a(AHDL_MEMVAR):
            return
        stms = self.usedef.get_stm_defining(dst_sig)
        if len(stms) > 1:
            return
        if self._has_depend_cycle(ahdl, dst_sig):
            return 
        if dst_sig.is_reg():
            dst_sig.del_tag('reg')
            dst_sig.add_tag('net')
        self.removes.append(ahdl)

    def visit_AHDL_IF(self, ahdl):
        for codes in ahdl.codes_list:
            self.visit_codes(codes)

    def visit_WAIT_EDGE(self, ahdl):
        if ahdl.codes:
            self.visit_codes(ahdl.codes)

    def visit_WAIT_VALUE(self, ahdl):
        if ahdl.codes:
            self.visit_codes(ahdl.codes)

    def _has_depend_cycle(self, start_stm, sig):
        visited = set()
        return self._has_depend_cycle_r(start_stm, sig, visited)
        
    def _has_depend_cycle_r(self, start_stm, sig, visited):
        stms = self.usedef.get_stm_using(sig)
        if start_stm in stms:
            return True
        for stm in stms:
            if stm in visited:
                continue
            visited.add(stm)
            defsigs = self.usedef.get_sig_defined_at(stm)
            for defsig in defsigs:
                if self._has_depend_cycle_r(start_stm, defsig, visited):
                    return True
        return False
