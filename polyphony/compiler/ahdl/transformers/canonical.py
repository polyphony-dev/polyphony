import functools
from collections import deque
from ..ahdl import *
from ..ahdltransformer import AHDLTransformer
from ...common.env import env


class Canonicalizer(AHDLTransformer):
    def process(self, hdlmodule):
        self.hdlmodule = hdlmodule
        self._add_reserved_signals()
        self._process_fsm()
        self._process_edge_detector()
        self._process_clock_counter()

    def _add_reserved_signals(self):
        if self.hdlmodule.scope.is_testbench():
            tags = {'reg'}
        else:
            tags = {'net', 'input'}
        self.hdlmodule.gen_sig('clk', 1, tags)
        self.hdlmodule.gen_sig('rst', 1, tags)

    def _process_fsm(self):
        for fsm in self.hdlmodule.fsms.values():
            self.current_state_sig = fsm.state_var
            self._add_state_constants(fsm)
            reset_blk = self._build_reset_block(fsm)
            case_blk = self._build_case_block(fsm)
            clk = self.hdlmodule.signal('clk')
            rst = self.hdlmodule.signal('rst')
            top_if = AHDL_IF((AHDL_VAR(rst, Ctx.LOAD), None), (reset_blk, case_blk))
            task = AHDL_EVENT_TASK(((clk, 'rising'),), top_if)
            self.hdlmodule.add_task(task)

    def _add_state_constants(self, fsm):
        i = 0
        for stg in fsm.stgs:
            for state in stg.states:
                self.hdlmodule.add_constant(state.name, i)
                i += 1
        fsm.state_var.width = i.bit_length()

    def _build_reset_block(self, fsm):
        resets = []
        for stm in sorted(fsm.reset_stms, key=lambda s: str(s)):
            if stm.dst.is_a(AHDL_VAR) and stm.dst.sig.is_net():
                continue
            resets.append(stm)
        for stg in fsm.stgs:
            if stg.is_main():
                main_stg = stg
        init_state_sig = self.hdlmodule.signal(main_stg.states[0].name)
        mv = AHDL_MOVE(AHDL_VAR(self.current_state_sig, Ctx.STORE),
                       AHDL_VAR(init_state_sig, Ctx.LOAD))
        resets.append(mv)
        return AHDL_BLOCK('', tuple(resets))

    def _build_case_block(self, fsm):
        case_items = self._build_case_items(fsm)
        case_stm = AHDL_CASE(AHDL_VAR(fsm.state_var, Ctx.LOAD), case_items)
        return AHDL_BLOCK('', (case_stm, ))

    def _build_case_items(self, fsm) -> tuple[AHDL_CASE_ITEM]:
        case_items = []
        for stg in sorted(fsm.stgs, key=lambda s: s.name):
            for state in stg.states:
                case_item_blk = self._build_case_item_block(fsm, state)
                case_item_sig = self.hdlmodule.signal(state.name)
                assert case_item_sig
                case_item_var = AHDL_VAR(case_item_sig, Ctx.LOAD)
                case_items.append(AHDL_CASE_ITEM(case_item_var, case_item_blk))
        return tuple(case_items)

    def _build_case_item_block(self, fsm, state) -> AHDL_BLOCK:
        new_codes = self._convert_codes(state.block.codes)
        return AHDL_BLOCK(state.name, new_codes)

    def _convert_codes(self, state_codes) -> tuple[AHDL_STM]:
        return tuple([self.visit(code) for code in state_codes])

    def _process_edge_detector(self):
        if not self.hdlmodule.edge_detectors:
            return
        clk = self.hdlmodule.signal('clk')
        vars = set([var for var, _, _ in self.hdlmodule.edge_detectors])
        for var in vars:
            # always @(posedge clk) sig_d <= sig;
            delayed_name = f'{var.hdl_name}_d'
            delayed_sig = self.hdlmodule.gen_sig(delayed_name, var.sig.width, {'reg'})
            assert var.ctx == Ctx.LOAD
            mv = AHDL_MOVE(AHDL_VAR(delayed_sig, Ctx.STORE), var)
            task = AHDL_EVENT_TASK(((clk, 'rising'),), mv)
            self.hdlmodule.add_task(task)

        detect_var_names = set()
        for var, old, new in self.hdlmodule.edge_detectors:
            delayed_name = f'{var.hdl_name}_d'
            detect_var_name = f'is_{var.hdl_name}_change_{old}_to_{new}'
            if detect_var_name in detect_var_names:
                continue
            detect_var_names.add(detect_var_name)
            delayed_sig = self.hdlmodule.signal(delayed_name)
            detect_var_sig = self.hdlmodule.signal(detect_var_name)
            # assign {detect_var} = ({delayed}=={old} && {sig}=={new});
            rhs = AHDL_OP('And',
                          AHDL_OP('Eq', AHDL_VAR(delayed_sig, Ctx.LOAD), old),
                          AHDL_OP('Eq', var, new))
            assign = AHDL_ASSIGN(AHDL_VAR(detect_var_sig, Ctx.STORE), rhs)
            self.hdlmodule.add_static_assignment(assign)

    def _process_clock_counter(self):
        if not self.hdlmodule.clock_signal:
            return
        name = self.hdlmodule.clock_signal.name
        width = self.hdlmodule.clock_signal.width
        clock_sig = self.hdlmodule.gen_sig(name, width, {'reg'})
        # always @(posedge clk) if (rst) {clock} <= 0; else {clock} <= {clock} + 1;
        then_blk = AHDL_BLOCK('', (AHDL_MOVE(AHDL_VAR(clock_sig, Ctx.STORE), AHDL_CONST(0)),))
        else_blk = AHDL_BLOCK('', (AHDL_MOVE(AHDL_VAR(clock_sig, Ctx.STORE),
                                             AHDL_OP('Add',
                                                     AHDL_VAR(clock_sig, Ctx.LOAD),
                                                     AHDL_CONST(1))),))
        clk = self.hdlmodule.signal('clk')
        rst = self.hdlmodule.signal('rst')
        if_stm = AHDL_IF((AHDL_VAR(rst, Ctx.LOAD), None), (then_blk, else_blk))
        task = AHDL_EVENT_TASK(((clk, 'rising'),), if_stm)
        self.hdlmodule.add_task(task)

    def visit_AHDL_META_OP(self, ahdl):
        method = 'visit_AHDL_META_OP_' + ahdl.op
        visitor = getattr(self, method, None)
        return visitor(ahdl)

    def visit_AHDL_META_OP_edge(self, ahdl):
        old, new = ahdl.args[0], ahdl.args[1]
        detect_vars = []
        for var in ahdl.args[2:]:
            detect_var_name = f'is_{var.sig.name}_change_{self.visit(old)}_to_{self.visit(new)}'
            detect_var_sig = self.hdlmodule.gen_sig(detect_var_name, 1, {'net'})
            detect_vars.append(AHDL_VAR(detect_var_sig, Ctx.LOAD))
        if len(detect_vars) > 1:
            return self.visit(AHDL_OP('And', *detect_vars))
        else:
            return self.visit(detect_vars[0])

    def visit_AHDL_META_OP_cond(self, ahdl):
        assert len(ahdl.args) % 3 == 0
        eqs = []
        for i in range(0, len(ahdl.args), 3):
            cond  = ahdl.args[i]
            value = ahdl.args[i + 1]
            port  = ahdl.args[i + 2]
            eqs.append(AHDL_OP(cond, port, value))
        cond = functools.reduce(lambda a, b: AHDL_OP('And', a, b), eqs)
        return self.visit(cond)

    def visit_AHDL_MOVE(self, ahdl):
        if ahdl.dst.is_a(AHDL_VAR) and ahdl.dst.sig.is_net():
            self.hdlmodule.add_static_assignment(AHDL_ASSIGN(ahdl.dst, ahdl.src))
            return AHDL_NOP('')
        elif ahdl.dst.is_a(AHDL_SUBSCRIPT) and ahdl.dst.memvar.sig.is_netarray():
            self.hdlmodule.add_static_assignment(AHDL_ASSIGN(ahdl.dst, ahdl.src))
            return AHDL_NOP('')
        src = self.visit(ahdl.src)
        dst = self.visit(ahdl.dst)
        return AHDL_MOVE(dst, src)

    def visit_AHDL_IO_READ(self, ahdl):
        assert False

    def visit_AHDL_IO_WRITE(self, ahdl):
        assert False

    def visit_AHDL_SEQ(self, ahdl):
        assert False

    def visit_AHDL_CALLEE_PROLOG(self, ahdl):
        assert False

    def visit_AHDL_CALLEE_EPILOG(self, ahdl):
        assert False

    def visit_AHDL_META_WAIT(self, ahdl):
        assert False

    def visit_AHDL_TRANSITION(self, ahdl):
        # convert AHDL_TRANSITION to AHDL_MOVE
        target_sig = self.hdlmodule.signal(ahdl.target_name)
        assert target_sig
        return AHDL_MOVE(AHDL_VAR(self.current_state_sig, Ctx.STORE),
                         AHDL_VAR(target_sig, Ctx.LOAD))


class FlattenClassFieldSignals(AHDLTransformer):
    def visit_AHDL_VAR(self, ahdl):
        if ahdl.is_local_var():
            return ahdl
        if ahdl.sig.sym.is_static() and ahdl.sig.sym.scope.is_class():
            new_sig = self.hdlmodule.gen_sig(ahdl.hdl_name, ahdl.sig.width, ahdl.sig.tags, ahdl.sig.sym)
            return AHDL_VAR(new_sig, ahdl.ctx)
        return ahdl

    def visit_AHDL_MEMVAR(self, ahdl):
        if ahdl.is_local_var():
            return ahdl
        if ahdl.sig.sym.is_static() and ahdl.sig.sym.scope.is_class():
            new_sig = self.hdlmodule.gen_sig(ahdl.hdl_name, ahdl.sig.width, ahdl.sig.tags, ahdl.sig.sym)
            return AHDL_MEMVAR(new_sig, ahdl.ctx)
        return ahdl
