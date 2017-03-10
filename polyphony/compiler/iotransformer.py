from .ahdl import *
from .ahdlvisitor import AHDLVisitor
from .utils import find_only_one_in


class IOTransformer(AHDLVisitor):
    def process(self, scope):
        if not scope.module_info:
            return
        self.module_info = scope.module_info
        for fsm in self.module_info.fsms.values():
            for stg in fsm.stgs:
                for state in stg.states:
                    self.current_parent = state
                    # we should use copy of codes because it might be changed
                    for code in state.codes[:]:
                        self.visit(code)

    def visit_AHDL_IO_READ_SEQ(self, ahdl, step):
        if ahdl.is_self:
            io = self.module_info.interfaces[ahdl.io.sig.name]
        elif ahdl.io.sig.is_extport():
            io = self.module_info.accessors[ahdl.io.sig.name]
        else:
            io = self.module_info.local_readers[ahdl.io.sig.name]
        return io.read_sequence(step, ahdl.dst)

    def visit_AHDL_IO_WRITE_SEQ(self, ahdl, step):
        if ahdl.is_self:
            io = self.module_info.interfaces[ahdl.io.sig.name]
        elif ahdl.io.sig.is_extport():
            io = self.module_info.accessors[ahdl.io.sig.name]
        else:
            io = self.module_info.local_writers[ahdl.io.sig.name]
        return io.write_sequence(step, ahdl.src)

    def visit_AHDL_SEQ(self, ahdl):
        method = 'visit_{}_SEQ'.format(ahdl.factor.__class__.__name__)
        visitor = getattr(self, method, None)
        if not visitor:
            return
        seq = visitor(ahdl.factor, ahdl.step)
        self.current_parent.codes.remove(ahdl)
        meta_wait = find_only_one_in(AHDL_META_WAIT, seq)
        if meta_wait:
            trans = self.current_parent.codes[-1]
            if trans.is_a(AHDL_TRANSITION):
                meta_wait.transition = trans
                self.current_parent.codes.remove(trans)
            else:
                assert False
        self.current_parent.codes = list(seq) + self.current_parent.codes

    def visit_AHDL_TRANSITION_IF(self, ahdl):
        for cond in ahdl.conds:
            if cond:
                self.visit(cond)
        for i, codes in enumerate(ahdl.codes_list):
            temp_parent = type('temp', (object,), {})
            temp_parent.codes = codes
            last_parent = self.current_parent
            self.current_parent = temp_parent
            # we should use copy of codes because it might be changed
            for code in codes[:]:
                self.visit(code)
            self.current_parent = last_parent
            ahdl.codes_list[i] = temp_parent.codes
