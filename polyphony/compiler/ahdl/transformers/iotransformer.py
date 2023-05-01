from collections import defaultdict
from ..ahdl import *
from ..ahdltransformer import AHDLTransformer
from ...common.common import fail
from ...common.errors import Errors


class IOTransformer(AHDLTransformer):
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
        assert False

    def visit_AHDL_CALLEE_EPILOG_SEQ(self, ahdl, step, step_n):
        if step == 0:
            valid = self.hdlmodule.signal(f'{self.hdlmodule.name}_valid')
            accept = self.hdlmodule.signal(f'{self.hdlmodule.name}_accept')
            set_valid = AHDL_MOVE(AHDL_VAR(valid, Ctx.STORE), AHDL_CONST(1))
            args = ['Eq', AHDL_CONST(1), AHDL_VAR(accept, Ctx.LOAD)]
            wait_accept = AHDL_META_WAIT("WAIT_COND", *args)
            return (set_valid, wait_accept)
        assert False

    def visit_AHDL_SEQ(self, ahdl):
        method = 'visit_{}_SEQ'.format(ahdl.factor.__class__.__name__)
        visitor = getattr(self, method, None)
        assert visitor
        seq = visitor(ahdl.factor, ahdl.step, ahdl.step_n)
        if id(ahdl) in self.hdlmodule.ahdl2dfgnode:
            _, node = self.hdlmodule.ahdl2dfgnode[id(ahdl)]
            for s in seq:
                self.hdlmodule.ahdl2dfgnode[id(s)] = (s, node)
        return seq

    def visit_AHDL_IO_READ(self, ahdl):
        return AHDL_MOVE(ahdl.dst, ahdl.io)

    def visit_AHDL_IO_WRITE(self, ahdl):
        return AHDL_MOVE(ahdl.io, ahdl.src)


class WaitTransformer(AHDLTransformer):
    def __init__(self):
        self.count = 0

    def visit_State(self, state):
        self._additional_states = []
        new_state = super().visit_State(state)
        if self._additional_states:
            return (new_state,) + tuple(self._additional_states)
        else:
            return new_state

    def visit_AHDL_BLOCK(self, ahdl):
        new_block = super().visit_AHDL_BLOCK(ahdl)
        meta_waits = [c for c in new_block.codes if c.is_a(AHDL_META_WAIT)]
        if meta_waits:
            new_block = self._transform_meta_wait(new_block, meta_waits)
        return new_block

    def _partition_codes(self, codes: list[AHDL_STM], delim: AHDL_STM) -> list[tuple[AHDL_STM]]:
        partitions: list[tuple[AHDL_STM]] = []
        part = []
        for c in codes:
            if c is delim:
                partitions.append(tuple(part))
                part = []
            else:
                part.append(c)
        partitions.append(tuple(part))
        return partitions

    def _build_waiting_state(self, cond, next_codes):
        waiting_state_name = f'{self.current_state.name}_waiting{self.count}'
        self.count += 1
        next_codes = tuple([self.visit(code) for code in next_codes])
        true_blk = AHDL_BLOCK('', next_codes)
        false_blk = AHDL_BLOCK('', (AHDL_TRANSITION(waiting_state_name),))
        wait_block = AHDL_IF((cond, None), (true_blk, false_blk))
        waiting_state = State(waiting_state_name,
                              AHDL_BLOCK('', (wait_block,)),
                              self.current_state.step + 1,
                              self.current_stg)
        return waiting_state

    def _transform_meta_wait(self, ahdlblk: AHDL_BLOCK, meta_waits):
        codes = ahdlblk.codes
        wait_ops = {
            'WAIT_COND':'cond',
            'WAIT_EDGE':'edge',
        }
        new_codes = list(codes)
        for meta_wait in reversed(meta_waits):
            partitions = self._partition_codes(new_codes, meta_wait)
            next_codes = partitions[1]
            cond = AHDL_META_OP(wait_ops[meta_wait.metaid], *meta_wait.args)
            waiting_state = self._build_waiting_state(cond, next_codes)
            true_blk = AHDL_BLOCK('', next_codes)
            false_codes = (AHDL_TRANSITION(waiting_state.name),)
            false_blk = AHDL_BLOCK('', false_codes)
            wait_block = AHDL_IF((cond, None), (true_blk, false_blk))
            # replace meta_wait
            idx = new_codes.index(meta_wait)
            new_codes.insert(idx, wait_block)
            for i in range(len(new_codes) - idx - 1):
                new_codes.pop()
            self._additional_states.append(waiting_state)
        return AHDL_BLOCK(ahdlblk.name, tuple(new_codes))