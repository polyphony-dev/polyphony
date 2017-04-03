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

    def visit_AHDL_MODULECALL_SEQ(self, ahdl, step, step_n):
        _, sub_info, connections, _ = self.module_info.sub_modules[ahdl.instance_name]
        assert len(connections) >= 1 + len(ahdl.args) + len(ahdl.returns)
        callacc = connections[0][1]
        argaccs = [acc for inf, acc in connections[1:len(ahdl.args) + 1]]
        retaccs = [acc for inf, acc in connections[len(ahdl.args) + 1:]]
        return callacc.call_sequence(step, step_n, argaccs, retaccs, ahdl, self.module_info.scope)

    def visit_AHDL_CALLEE_PROLOG_SEQ(self, ahdl, step, step_n):
        callinf = self.module_info.interfaces['']
        return callinf.callee_prolog(step, ahdl.name)

    def visit_AHDL_CALLEE_EPILOG_SEQ(self, ahdl, step, step_n):
        callinf = self.module_info.interfaces['']
        return callinf.callee_epilog(step, ahdl.name)

    def visit_AHDL_IO_READ_SEQ(self, ahdl, step, step_n):
        if ahdl.is_self:
            io = self.module_info.interfaces[ahdl.io.sig.name]
        elif ahdl.io.sig.is_extport():
            io = self.module_info.accessors[ahdl.io.sig.name]
        else:
            io = self.module_info.local_readers[ahdl.io.sig.name]
        return io.read_sequence(step, ahdl.dst)

    def visit_AHDL_IO_WRITE_SEQ(self, ahdl, step, step_n):
        if ahdl.is_self:
            io = self.module_info.interfaces[ahdl.io.sig.name]
        elif ahdl.io.sig.is_extport():
            io = self.module_info.accessors[ahdl.io.sig.name]
        else:
            io = self.module_info.local_writers[ahdl.io.sig.name]
        return io.write_sequence(step, ahdl.src)

    def _is_continuous_access_to_mem(self, ahdl):
        other_memnodes = [c.factor.mem.memnode for c in self.current_parent.codes
                          if c.is_a([AHDL_SEQ]) and
                          c.factor.is_a([AHDL_LOAD, AHDL_STORE]) and
                          c.factor is not ahdl]
        for memnode in other_memnodes:
            if memnode is ahdl.mem.memnode:
                return True
        return False

    def visit_AHDL_LOAD_SEQ(self, ahdl, step, step_n):
        is_continuous = self._is_continuous_access_to_mem(ahdl)
        memacc = self.module_info.local_readers[ahdl.mem.sig.name]
        return memacc.read_sequence(step, ahdl.offset, ahdl.dst, is_continuous)

    def visit_AHDL_STORE_SEQ(self, ahdl, step, step_n):
        is_continuous = self._is_continuous_access_to_mem(ahdl)
        memacc = self.module_info.local_writers[ahdl.mem.sig.name]
        return memacc.write_sequence(step, ahdl.offset, ahdl.src, is_continuous)

    def visit_AHDL_SEQ(self, ahdl):
        method = 'visit_{}_SEQ'.format(ahdl.factor.__class__.__name__)
        visitor = getattr(self, method, None)
        assert visitor
        seq = visitor(ahdl.factor, ahdl.step, ahdl.step_n)
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
