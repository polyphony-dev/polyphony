from .ahdl import *
from .ahdlvisitor import AHDLVisitor
from .stg import State, PipelineState, PipelineStage
from .utils import find_only_one_in


class IOTransformer(AHDLVisitor):
    def __init__(self):
        self.removes = []

    def process(self, hdlmodule):
        self.hdlmodule = hdlmodule
        for fsm in self.hdlmodule.fsms.values():
            for stg in fsm.stgs:
                for state in stg.states:
                    if isinstance(state, PipelineState):
                        for stage in state.stages:
                            self.current_parent = stage
                            # we should use copy of codes because it might be changed
                            for code in stage.codes[:]:
                                self.visit(code)
                    elif isinstance(state, State):
                        self.current_parent = state
                        # we should use copy of codes because it might be changed
                        for code in state.codes[:]:
                            self.visit(code)
        self.post_process()

    def post_process(self):
        for state, code in self.removes:
            if code in state.codes:
                state.codes.remove(code)

    def visit_AHDL_MODULECALL_SEQ(self, ahdl, step, step_n):
        _, sub_module, connections, _ = self.hdlmodule.sub_modules[ahdl.instance_name]
        assert len(connections['']) + len(connections['ret']) >= 1 + len(ahdl.args) + len(ahdl.returns)
        conns = connections['']
        callacc = conns[0][1]
        argaccs = []
        argaccs = [acc for inf, acc in conns[1:]]
        ret_conns = connections['ret']
        retaccs = [acc for inf, acc in ret_conns]
        return callacc.call_sequence(step, step_n, argaccs, retaccs, ahdl)

    def visit_AHDL_CALLEE_PROLOG_SEQ(self, ahdl, step, step_n):
        callinf = self.hdlmodule.interfaces['']
        return callinf.callee_prolog(step, ahdl.name)

    def visit_AHDL_CALLEE_EPILOG_SEQ(self, ahdl, step, step_n):
        callinf = self.hdlmodule.interfaces['']
        return callinf.callee_epilog(step, ahdl.name)

    def visit_AHDL_IO_READ_SEQ(self, ahdl, step, step_n):
        if ahdl.is_self:
            io = self.hdlmodule.find_interface(ahdl.io.sig.name)
        elif ahdl.io.sig.is_extport():
            io = self.hdlmodule.accessors[ahdl.io.sig.name]
        else:
            io = self.hdlmodule.local_readers[ahdl.io.sig.name]
        if isinstance(self.current_parent, PipelineStage):
            stage = self.current_parent
            return io.pipelined_read_sequence(step, step_n, ahdl.dst, stage)
        else:
            return io.read_sequence(step, step_n, ahdl.dst)

    def visit_AHDL_IO_WRITE_SEQ(self, ahdl, step, step_n):
        if ahdl.is_self:
            io = self.hdlmodule.find_interface(ahdl.io.sig.name)
        elif ahdl.io.sig.is_extport():
            io = self.hdlmodule.accessors[ahdl.io.sig.name]
        else:
            io = self.hdlmodule.local_writers[ahdl.io.sig.name]
        if isinstance(self.current_parent, PipelineStage):
            stage = self.current_parent
            return io.pipelined_write_sequence(step, step_n, ahdl.src, stage)
        else:
            return io.write_sequence(step, step_n, ahdl.src)

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
        memacc = self.hdlmodule.local_readers[ahdl.mem.sig.name]
        if isinstance(self.current_parent, PipelineStage):
            stage = self.current_parent
            return memacc.pipelined(stage).read_sequence(step, step_n, ahdl.offset, ahdl.dst, is_continuous)
        else:
            return memacc.read_sequence(step, step_n, ahdl.offset, ahdl.dst, is_continuous)

    def visit_AHDL_STORE_SEQ(self, ahdl, step, step_n):
        is_continuous = self._is_continuous_access_to_mem(ahdl)
        memacc = self.hdlmodule.local_writers[ahdl.mem.sig.name]
        if isinstance(self.current_parent, PipelineStage):
            stage = self.current_parent
            return memacc.pipelined(stage).write_sequence(step, step_n, ahdl.offset, ahdl.src, is_continuous)
        else:
            return memacc.write_sequence(step, step_n, ahdl.offset, ahdl.src, is_continuous)

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
                self.removes.append((self.current_parent, trans))
            elif isinstance(self.current_parent, PipelineStage):
                pass
            else:
                meta_wait_ = find_only_one_in(AHDL_META_WAIT, self.current_parent.codes)
                assert meta_wait_
                meta_wait.transition = meta_wait_.transition

        # TODO: workaround
        if self.current_parent.codes and self.current_parent.codes[0].is_a(AHDL_PIPELINE_GUARD):
            self.current_parent.codes = self.current_parent.codes[0:1] + list(seq) + self.current_parent.codes[1:]
        else:
            self.current_parent.codes = list(seq) + self.current_parent.codes

    def visit_AHDL_IF(self, ahdl):
        for cond in ahdl.conds:
            if cond:
                self.visit(cond)
        for i, codes in enumerate(ahdl.codes_list):
            temp_parent = type('temp', (object,), {})
            temp_parent.codes = codes
            if isinstance(self.current_parent, PipelineStage):
                temp_parent.parent_state = self.current_parent.parent_state
            last_parent = self.current_parent
            self.current_parent = temp_parent
            # we should use copy of codes because it might be changed
            for code in codes[:]:
                self.visit(code)
            self.current_parent = last_parent
            ahdl.codes_list[i] = temp_parent.codes


class WaitTransformer(AHDLVisitor):
    def __init__(self):
        self.count = 0

    def process(self, hdlmodule):
        self.hdlmodule = hdlmodule
        for fsm in self.hdlmodule.fsms.values():
            for stg in fsm.stgs:
                for state in stg.states:
                    if isinstance(state, PipelineState):
                        for stage in state.stages:
                            self.current_parent = stage
                            self.transform_meta_wait(stage.codes)
                    elif isinstance(state, State):
                        self.current_parent = state
                        self.transform_meta_wait(state.codes)

    def transform_meta_wait(self, codes):
        meta_waits = [c for c in codes if c.is_a(AHDL_META_WAIT)]
        if len(meta_waits) <= 1:
            return

        multi_wait = AHDL_META_MULTI_WAIT(self.count)
        self.count += 1
        multi_wait.transition = meta_waits[0].transition
        for w in meta_waits:
            w.transition = None
            multi_wait.append(w)
            codes.remove(w)
        codes.append(multi_wait)

        multi_wait.build_transition()
        for i in range(len(meta_waits)):
            ahdl_var = multi_wait.latch_var(i)
            sig = self.hdlmodule.gen_sig(ahdl_var.name, 1)
            self.hdlmodule.add_internal_reg(sig)
