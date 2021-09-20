from collections import defaultdict
from ..ahdl import *
from ..ahdlvisitor import AHDLVisitor
from ..stg import State
from ...common.common import fail
from ...common.errors import Errors


class IOTransformer(AHDLVisitor):
    def __init__(self):
        super().__init__()
        self.removes = []

    def process(self, hdlmodule):
        self.hdlmodule = hdlmodule
        self.current_block = None
        self.current_stage = None
        self.old_codes = []
        super().process(hdlmodule)
        self.post_process()

    def process_state(self, state):
        self.reduce_rewrite(state)
        super().process_state(state)

    def post_process(self):
        for state, code in self.removes:
            if code in state.codes:
                state.codes.remove(code)

    def call_sequence(self, step, step_n, args, returns, ahdl_call):
        seq = []
        inst_name = ahdl_call.instance_name
        valid = self.hdlmodule.signal(f'{inst_name}_valid')
        ready = self.hdlmodule.signal(f'{inst_name}_ready')
        accept = self.hdlmodule.signal(f'{inst_name}_valid')

        if step == 0:
            seq = [AHDL_MOVE(AHDL_VAR(ready, Ctx.STORE), AHDL_CONST(1))]
            for acc, arg in zip(args, ahdl_call.args):
                assert not arg.is_a(AHDL_MEMVAR)
                seq.append(AHDL_MOVE(AHDL_VAR(acc, Ctx.STORE), arg))
        elif step == 1:
            seq = [AHDL_MOVE(AHDL_VAR(ready, Ctx.STORE), AHDL_CONST(0))]
            args = ['Eq', AHDL_CONST(1), AHDL_VAR(valid, Ctx.LOAD)]
            seq.append(AHDL_META_WAIT('WAIT_COND', *args))
            for acc, ret in zip(returns, ahdl_call.returns):
                seq.append(AHDL_MOVE(ret, AHDL_VAR(acc, Ctx.LOAD)))
            seq.append(AHDL_MOVE(AHDL_VAR(accept, Ctx.STORE), AHDL_CONST(1)))
        elif step == 2:
            seq.append(AHDL_MOVE(AHDL_VAR(accept, Ctx.STORE), AHDL_CONST(0)))
        return tuple(seq)

    def visit_AHDL_MODULECALL_SEQ(self, ahdl, step, step_n):
        _, sub_module, connections, _ = self.hdlmodule.sub_modules[ahdl.instance_name]
        args = []
        returns = []
        for sig, acc in connections:
            if sig.is_ctrl():
                continue
            elif sig.is_input():
                args.append(acc)
            elif sig.is_output():
                returns.append(acc)
        return self.call_sequence(step, step_n, args, returns, ahdl)

    def visit_AHDL_CALLEE_PROLOG_SEQ(self, ahdl, step, step_n):
        if step == 0:
            valid = self.hdlmodule.signal(f'{self.hdlmodule.name}_valid')
            ready = self.hdlmodule.signal(f'{self.hdlmodule.name}_ready')
            unset_valid = AHDL_MOVE(AHDL_VAR(valid, Ctx.STORE), AHDL_CONST(0))
            args = ['Eq', AHDL_CONST(1), AHDL_VAR(ready, Ctx.LOAD)]
            wait_ready = AHDL_META_WAIT("WAIT_COND", *args)
            return (unset_valid, wait_ready)

    def visit_AHDL_CALLEE_EPILOG_SEQ(self, ahdl, step, step_n):
        if step == 0:
            valid = self.hdlmodule.signal(f'{self.hdlmodule.name}_valid')
            accept = self.hdlmodule.signal(f'{self.hdlmodule.name}_accept')
            set_valid = AHDL_MOVE(AHDL_VAR(valid, Ctx.STORE), AHDL_CONST(1))
            args = ['Eq', AHDL_CONST(1), AHDL_VAR(accept, Ctx.LOAD)]
            wait_accept = AHDL_META_WAIT("WAIT_COND", *args)
            return (set_valid, wait_accept)

    def visit_AHDL_SEQ(self, ahdl):
        method = 'visit_{}_SEQ'.format(ahdl.factor.__class__.__name__)
        visitor = getattr(self, method, None)
        assert visitor
        seq = visitor(ahdl.factor, ahdl.step, ahdl.step_n)
        offs = self.current_block.codes.index(ahdl)
        self.current_block.codes.remove(ahdl)
        for i, s in enumerate(seq):
            self.current_block.codes.insert(offs + i, s)
        if ahdl in self.hdlmodule.ahdl2dfgnode:
            node = self.hdlmodule.ahdl2dfgnode[ahdl]
            for s in seq:
                self.hdlmodule.ahdl2dfgnode[s] = node

    def visit_AHDL_IO_READ(self, ahdl):
        mv = AHDL_MOVE(ahdl.dst, ahdl.io)
        idx = self.current_block.codes.index(ahdl)
        self.current_block.codes.remove(ahdl)
        self.current_block.codes.insert(idx, mv)

    def visit_AHDL_IO_WRITE(self, ahdl):
        mv = AHDL_MOVE(ahdl.io, ahdl.src)
        idx = self.current_block.codes.index(ahdl)
        self.current_block.codes.remove(ahdl)
        self.current_block.codes.insert(idx, mv)

    def visit_AHDL_IF(self, ahdl):
        for cond in ahdl.conds:
            if cond:
                self.visit(cond)
        for i, ahdlblk in enumerate(ahdl.blocks):
            self.visit(ahdlblk)

    def visit_AHDL_BLOCK(self, ahdl):
        old_block = self.current_block
        self.current_block = ahdl
        # we should save copy of codes because it might be changed
        self.old_codes = ahdl.codes[:]
        for code in self.old_codes:
            self.visit(code)
        self.current_block = old_block

    def visit_PipelineStage(self, ahdl):
        self.current_stage = ahdl
        self.visit_AHDL_BLOCK(ahdl)

    def reduce_rewrite(self, state):
        iowrites = defaultdict(list)
        for c in state.codes:
            if c.is_a(AHDL_IO_WRITE):
                iowrites[c.io.sig].append(c)
        for sig, ios in iowrites.items():
            if len(ios) >= 2:
                if sig.is_rewritable():
                    for io in ios[:-1]:
                        state.codes.remove(io)
                else:
                    node = self.hdlmodule.ahdl2dfgnode[ios[1]]
                    fail(node.tag, Errors.RULE_TIMED_PORT_IS_OVERWRITTEN, [sig.sym.ancestor])


class WaitTransformer(AHDLVisitor):
    def __init__(self):
        self.count = 0

    def visit_AHDL_BLOCK(self, ahdl):
        super().visit_AHDL_BLOCK(ahdl)
        self.transform_meta_wait(ahdl)

    def _partition_codes(self, codes, delim):
        partitions = []
        part = []
        for c in codes:
            if c is delim:
                partitions.append(part)
                part = []
            else:
                part.append(c)
        partitions.append(part)
        return partitions

    def _build_waiting_state(self, cond, next_codes):
        waiting_state = State(f'{self.current_state.name}_waiting{self.count}',
                              self.current_state.step + 1,
                              [], self.current_stg)
        self.count += 1
        true_blk = AHDL_BLOCK('', next_codes)
        false_blk = AHDL_BLOCK('', [AHDL_TRANSITION(waiting_state)])
        wait_block = AHDL_IF([cond, None], [true_blk, false_blk])
        waiting_state.codes = [wait_block]
        idx = self.current_stg.states.index(self.current_state)
        self.current_stg.states.insert(idx + 1, waiting_state)
        return waiting_state

    def transform_meta_wait(self, ahdlblk):
        meta_waits = [c for c in ahdlblk.codes if c.is_a(AHDL_META_WAIT)]
        codes = ahdlblk.codes
        wait_ops = {
            'WAIT_COND':'cond',
            'WAIT_EDGE':'edge',
        }
        for meta_wait in reversed(meta_waits):
            partitions = self._partition_codes(codes, meta_wait)
            next_codes = partitions[1]
            cond = AHDL_META_OP(wait_ops[meta_wait.metaid], *meta_wait.args)
            waiting_state = self._build_waiting_state(cond, next_codes)
            true_blk = AHDL_BLOCK('', next_codes)
            if meta_wait.waiting_stms:
                false_codes = meta_wait.waiting_stms[:] + [AHDL_TRANSITION(waiting_state)]
            else:
                false_codes = [AHDL_TRANSITION(waiting_state)]
            false_blk = AHDL_BLOCK('', false_codes)
            wait_block = AHDL_IF([cond, None], [true_blk, false_blk])
            # replace meta_wait
            idx = codes.index(meta_wait)
            codes.insert(idx, wait_block)
            for i in range(len(codes) - idx - 1):
                codes.pop()
