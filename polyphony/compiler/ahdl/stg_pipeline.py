from collections import defaultdict
import dataclasses
from dataclasses import dataclass
from .ahdl import *
from .stgbuilder import State, STGItemBuilder, ScheduledItemQueue
from .analysis.ahdlusedef import AHDLUseDefDetector
from .ahdltransformer import AHDLTransformer
from ..ir.ir import MOVE, CJUMP
from ..ir.irhelper import qualified_symbols
from logging import getLogger
logger = getLogger(__name__)


@dataclass(frozen=True)
class PipelineState(State):
    pass


@dataclass(frozen=True)
class PipelineStage(State):
    has_enable:bool = False
    has_hold:bool = False


class PipelineStateHelper(object):
    def __init__(self, name, nstate, first_valid_signal, stg):
        assert isinstance(name, str)
        assert 1 <= nstate
        self._name = name
        self._stg = stg
        self.substate_var = stg.hdlmodule.gen_sig(f'{name}_state',
                                                  nstate.bit_length(),
                                                  {'reg', 'pipeline_ctrl'})
        self.whole_moves = []
        if first_valid_signal:
            self.valid_signals = {0:first_valid_signal}
        else:
            self.valid_signals = {}
        self.ready_signals = {}
        self.enable_signals = {}
        self.hold_signals = {}
        self.last_signals = {}
        self.exit_signals = {}
        self.moves = {}

    def _pipeline_signal(self, signal_name, signals, idx, is_reg) -> Signal:
        assert idx >= 0
        if idx not in signals:
            name = f'{self._name}_{idx}_{signal_name}'
            if is_reg:
                tags = {'reg', 'pipeline_ctrl'}
            else:
                tags = {'net', 'pipeline_ctrl'}
            new_sig = self._stg.hdlmodule.gen_sig(name, 1, tags)
            signals[idx] = new_sig
        return signals[idx]

    def valid_signal(self, idx) -> Signal:
        return self._pipeline_signal('valid', self.valid_signals, idx, True)

    def valid_exp(self, idx)  -> AHDL_EXP:
        ready = self.ready_signal(idx)
        if idx > 0:
            # hold ? ready : ready & prev_valid
            hold = self.hold_signal(idx)
            valid_prev = self.valid_signal(idx - 1)
            return AHDL_IF_EXP(AHDL_VAR(hold, Ctx.LOAD),
                               AHDL_VAR(ready, Ctx.LOAD),
                               AHDL_OP('BitAnd',
                                       AHDL_VAR(ready, Ctx.LOAD),
                                       AHDL_VAR(valid_prev, Ctx.LOAD)))
        else:
            return AHDL_VAR(ready, Ctx.LOAD)

    def ready_signal(self, idx) -> Signal:
        return self._pipeline_signal('ready', self.ready_signals, idx, False)

    def enable_signal(self, idx) -> Signal:
        return self._pipeline_signal('enable', self.enable_signals, idx, False)

    def hold_signal(self, idx) -> Signal:
        return self._pipeline_signal('hold', self.hold_signals, idx, True)

    def last_signal(self, idx) -> Signal:
        return self._pipeline_signal('last', self.last_signals, idx, True)

    def exit_signal(self, idx) -> Signal:
        return self._pipeline_signal('exit', self.exit_signals, idx, True)

    def new_stage(self, step, codes, has_enable, has_hold) -> PipelineStage:
        stage_name = f'{self._name}_{step}'
        stage = PipelineStage(stage_name, AHDL_BLOCK('', tuple(codes)), step, self._stg, has_enable=has_enable, has_hold=has_hold)
        return stage

    def add_global_move(self, sym, mv):
        if sym in self.moves:
            mv_ = self.moves[sym]
            mv_.src = AHDL_OP('BitOr', mv_.src, mv.src)
        else:
            self.moves[sym] = mv
            self.whole_moves.append(mv)


class PipelineBuilder(STGItemBuilder):
    def __init__(self, scope, stg, blk2states):
        super().__init__(scope, stg, blk2states)
        self.is_finite_loop = True

    def build(self, dfg, is_main):
        self.stages:list[PipelineStage] = []
        self.n_substate = dfg.ii
        blk_name = dfg.region.head.nametag + str(dfg.region.head.num)
        state_name = self.stg.name + '_' + blk_name + '_P'
        pstate_helper = PipelineStateHelper(state_name, self.n_substate, None, self.stg)

        self.scheduled_items = ScheduledItemQueue()
        self._build_scheduled_items(dfg)
        self._build_pipeline_stages(pstate_helper)

        # customize point
        exit_stm = self.post_build(dfg, pstate_helper)

        end_codes = [exit_stm]
        if not exit_stm.is_a([AHDL_TRANSITION, AHDL_TRANSITION_IF]):
            pipe_end_stm = AHDL_TRANSITION(state_name)
            end_codes.append(pipe_end_stm)
        case_items = []
        for i in range(self.n_substate):
            stages = []
            for j in range(i, len(self.stages), self.n_substate):
                stages.append(self.stages[j])
            substate_codes:list[AHDL_STM] = stages
            if i == self.n_substate - 1:
                next = 0
            else:
                next = i + 1
            mv_next_state = AHDL_MOVE(AHDL_VAR(pstate_helper.substate_var, Ctx.STORE),
                                      AHDL_CONST(next))

            substate_codes.append(mv_next_state)
            case_item = AHDL_CASE_ITEM(AHDL_CONST(i), AHDL_BLOCK('', tuple(substate_codes)))
            case_items.append(case_item)
        whole_moves_blk = AHDL_BLOCK('', tuple(pstate_helper.whole_moves))
        pipeline_state_codes:tuple[AHDL_STM] = (
            whole_moves_blk,
            AHDL_CASE(AHDL_VAR(pstate_helper.substate_var, Ctx.LOAD), tuple(case_items)),
         ) + tuple(end_codes)
        pipeline_state = PipelineState(state_name, AHDL_BLOCK('', pipeline_state_codes), 0, self.stg)

        for blk in dfg.region.blocks():
            self.blk2states[blk.name] = [pipeline_state]
        self.stg.add_states([pipeline_state])

    def post_build(self, dfg, pstate_helper) -> AHDL_STM:
        pass

    def _is_stall_free(self):
        for items in self.scheduled_items.queue.values():
            for item, _ in items:
                assert isinstance(item, AHDL)
                if item.find_ahdls(AHDL_META_WAIT):
                    return False
        return True

    def _build_pipeline_stages(self, pstate_helper):
        maxstep = max([step for (step, _) in self.scheduled_items.queue.items()])
        is_stall_free = self._is_stall_free()
        for step in range(maxstep + 1):
            if step in self.scheduled_items.queue:
                codes = []
                for item, _ in self.scheduled_items.queue[step]:
                    assert isinstance(item, AHDL)
                    codes.append(item)
            else:
                codes = [AHDL_NOP('empty stage')]
            stage = self._make_stage(pstate_helper, step, codes, is_stall_free)
            self.stages.append(stage)
            assert len(self.stages) == step + 1, f'stages {len(self.stages)} step {step}'

        # Execute after all stages are created
        self._transform_wait_function(pstate_helper)

        # TODO: _transform_wait_functionに依存していなければStage生成と同時に行う
        new_stages = []
        for stage in self.stages:
            new_stage = self._add_pipeline_guard(pstate_helper, stage)
            if is_stall_free:
                new_stage = self._add_control_chain_no_stall(pstate_helper, new_stage)
            else:
                self._add_control_chain(pstate_helper, stage)
            new_stages.append(new_stage)
        self.stages = new_stages
        self._process_register_slices(pstate_helper)

    def _process_register_slices(self, pstate_helper):
        # Analysis and inserting register slices between pileline stages
        stm2stage_num = self._make_stm2stage_num(pstate_helper)
        detector = AHDLUseDefDetector()
        for stage in self.stages:
            detector.current_state = stage
            detector.visit(stage)
        usedef = detector.table

        reg_slice_replace_table:dict[tuple, tuple] = {}
        reg_slice_moves:dict[int, list] = defaultdict(list)
        for sig in usedef.get_all_def_sigs():
            if sig.is_pipeline_ctrl():
                continue
            defs = usedef.get_def_stms(sig)
            d = list(defs)[0]
            d_stage_n = stm2stage_num[d]
            uses = usedef.get_use_stms(sig)
            use_max_distances = 0
            for u in uses:
                u_stage_n = stm2stage_num[u]
                distance = u_stage_n - d_stage_n
                #assert 0 <= distance, '{} {}'.format(d, u)
                if use_max_distances < distance:
                    use_max_distances = distance
            if (1 < use_max_distances or
                    ((sig.is_induction() or sig.is_net()) and 0 < use_max_distances)):
                logger.debug(f'process register slice for {sig}')
                replaces, moves = self._create_register_slice_info(sig,
                    d_stage_n, d_stage_n + use_max_distances,
                    usedef, stm2stage_num)
                reg_slice_replace_table.update(replaces)
                for key, v in moves.items():
                    reg_slice_moves[key].extend(v)
        logger.debug(reg_slice_replace_table)
        logger.debug(reg_slice_moves)
        transformer = AHDLRegisterSliceTransformer(reg_slice_replace_table, reg_slice_moves, self.hdlmodule)
        new_stages = []
        for stage in self.stages:
            new_stage = transformer.visit(stage)
            new_stages.append(new_stage)
            logger.debug(stage)
            logger.debug('---')
            logger.debug(new_stage)
        self.stages = new_stages

    def _make_stage(self, pstate_helper, step, codes, is_stall_free) -> PipelineStage:
        has_enable = False
        has_hold = False
        if step == 0 and self.is_finite_loop:
            has_enable = True
        elif step > 0:
            has_hold = not is_stall_free
        for c in codes:
            if c.find_ahdls(AHDL_META_WAIT):
                has_enable = True
                break
        return pstate_helper.new_stage(step, codes, has_enable, has_hold)

    def _transform_wait_function(self, pstate_helper):
        multi_assign_vars = defaultdict(list)
        removes = []
        for step, stage in enumerate(self.stages):
            for code in stage.block.codes[:]:
                if code.is_a(AHDL_META_WAIT):
                    assert stage.has_enable
                    enable_sig = pstate_helper.enable_signal(step)
                    enable_cond = AHDL_OP(*code.args)
                    assert False, 'TODO'
                    stage.enable = AHDL_MOVE(AHDL_VAR(enable_sig, Ctx.STORE), enable_cond)
                    removes.append((stage, code))
                elif code.is_a([AHDL_NOP, AHDL_TRANSITION]):
                    removes.append((stage, code))
                elif code.is_a(AHDL_MOVE) and code.dst.is_a(AHDL_VAR) and not code.dst.sig.is_net():
                    multi_assign_vars[code.dst.sig].append((step, stage, code))
        for sig, srcs in multi_assign_vars.items():
            rhs = None
            if len(srcs) > 1:
                for step, stage, code in reversed(srcs):
                    removes.append((stage, code))
            else:
                continue
            for step, _, code in reversed(srcs):
                src = code.src
                valid = pstate_helper.valid_signal(step)
                if rhs is None:
                    rhs = src
                else:
                    rhs = AHDL_IF_EXP(AHDL_VAR(valid, Ctx.LOAD), src, rhs)
            pstate_helper.add_global_move(sig.name, AHDL_MOVE(AHDL_VAR(sig, Ctx.STORE), rhs))
        # FIXME:
        for stage, code in removes:
            stage.block.codes.remove(code)

    def _add_pipeline_guard(self, pstate_helper, stage) -> PipelineStage:
        guarded_codes = []
        stage_codes = list(stage.block.codes)
        for c in stage.block.codes:
            if self._check_guard_need(c):
                guarded_codes.append(c)
                stage_codes.remove(c)
        if stage.step == 0:
            if stage.has_enable:
                guard_cond = AHDL_VAR(pstate_helper.ready_signal(0), Ctx.LOAD)
            else:
                guard_cond = AHDL_CONST(1)
        else:
            guard_cond = AHDL_VAR(pstate_helper.valid_signal(stage.step - 1), Ctx.LOAD)
        guard = AHDL_PIPELINE_GUARD(guard_cond, tuple(guarded_codes))
        stage_codes.insert(0, guard)
        return dataclasses.replace(stage, block=AHDL_BLOCK(stage.name, tuple(stage_codes)))

    def _add_control_chain(self, pstate_helper, stage):
        if stage.step == 0:
            v_now = pstate_helper.valid_signal(stage.step)
            if stage.has_enable:
                v_prev = pstate_helper.enable_signal(stage.step)
            else:
                v_prev = None
        else:
            v_now = pstate_helper.valid_signal(stage.step)
            v_prev = pstate_helper.valid_signal(stage.step - 1)
        is_last = stage.step == len(self.stages) - 1

        r_now = pstate_helper.ready_signal(stage.step)
        if not is_last:
            r_next = AHDL_VAR(pstate_helper.ready_signal(stage.step + 1), Ctx.LOAD)
        else:
            r_next = AHDL_CONST(1)
        if stage.has_enable:
            en = AHDL_VAR(pstate_helper.enable_signal(stage.step), Ctx.LOAD)
            # if stage.is_source:
            #     if len(self.stages) > (stage.step + 1):
            #         # ~next_hold & enable
            #         inv_next_hold = AHDL_OP('Invert',
            #                                 AHDL_VAR(pstate_helper.hold_signal(stage.step + 1), Ctx.LOAD))
            #         ready_rhs = AHDL_OP('BitAnd', inv_next_hold, en)
            #     else:
            #         ready_rhs = en
            # else:
            #     ready_rhs = AHDL_OP('BitAnd', r_next, en)
            ready_rhs = AHDL_OP('BitAnd', r_next, en)
        else:
            ready_rhs = r_next
        ready_stm = AHDL_MOVE(AHDL_VAR(r_now, Ctx.STORE), ready_rhs)
        # FIXME:
        stage.block.codes.append(ready_stm)

        if stage.has_hold:
            #hold = hold ? (!ready) : (valid & !ready);
            hold = pstate_helper.hold_signal(stage.step)
            if_lhs = AHDL_OP('Invert', AHDL_VAR(r_now, Ctx.LOAD))
            if_rhs = AHDL_OP('BitAnd',
                             AHDL_OP('Invert', AHDL_VAR(r_now, Ctx.LOAD)),
                             AHDL_VAR(v_prev, Ctx.LOAD))
            hold_rhs = AHDL_IF_EXP(AHDL_VAR(hold, Ctx.LOAD), if_lhs, if_rhs)
            hold_stm = AHDL_MOVE(AHDL_VAR(hold, Ctx.STORE), hold_rhs)
            # FIXME:
            stage.block.codes.append(hold_stm)

        if not is_last:
            valid_rhs = pstate_helper.valid_exp(stage.step)
            set_valid = AHDL_MOVE(AHDL_VAR(v_now, Ctx.STORE),
                                  valid_rhs)
            # FIXME:
            stage.block.codes.append(set_valid)

    def _make_stm2stage_num(self, pstate_helper):
        def _make_stm2stage_num_rec(codes):
            for c in codes:
                stm2stage_num[c] = i
                if c.is_a(AHDL_IF):
                    for ahdlblk in c.blocks:
                        if ahdlblk.is_a(AHDL_BLOCK):
                            _make_stm2stage_num_rec(ahdlblk.codes)
                        else:
                            _make_stm2stage_num_rec([ahdlblk])
        stm2stage_num = {}
        for i, stage in enumerate(self.stages):
            _make_stm2stage_num_rec(stage.block.codes)
        return stm2stage_num

    def _check_guard_need(self, ahdl):
        if (ahdl.is_a(AHDL_PROCCALL) or
                ahdl.is_a(AHDL_IF) or
                (ahdl.is_a(AHDL_MOVE) and ((ahdl.dst.is_a(AHDL_VAR) and ahdl.dst.sig.is_reg()) or
                                           ahdl.dst.is_a(AHDL_SUBSCRIPT))) or
                ahdl.is_a(AHDL_SEQ)):
            return True
        return False

    def _create_register_slice_info(self, sig, start_n, end_n, usedef, stm2stage_num) -> tuple[dict, dict]:
        defs = usedef.get_def_stms(sig)
        assert len(defs) == 1
        d = list(defs)[0]
        d_num = stm2stage_num[d]
        is_normal_reg = True if sig.is_reg() and not sig.is_induction() else False
        if is_normal_reg:
            start_n += 1
        for num in range(start_n, end_n + 1):
            if num == d_num:
                continue
            if is_normal_reg and (num - d_num) == 1:
                continue
            new_name = f'{sig.name}_{num}'  # use previous stage variable
            tags = sig.tags.copy()
            if 'net' in tags:
                tags.remove('net')
                tags.add('reg')
            self.hdlmodule.gen_sig(new_name, sig.width, tags, sig.sym)

        reg_replace_table:dict[tuple, tuple] = {}
        reg_slice_moves:dict[int, list] = defaultdict(list)
        for u in usedef.get_use_stms(sig):
            num = stm2stage_num[u]
            if num == d_num:
                continue
            if is_normal_reg and (num - d_num) == 1:
                continue
            new_name = f'{sig.name}_{num}'
            new_sig = self.hdlmodule.signal(new_name)

            key = (id(u), sig)
            assert key not in reg_replace_table
            reg_replace_table[key] = (new_sig,)
        for num in range(start_n, end_n):
            # first slice uses original
            if num == start_n:
                prev_sig = sig
            else:
                prev_name = f'{sig.name}_{num}'
                prev_sig = self.hdlmodule.signal(prev_name)
            cur_name = f'{sig.name}_{num + 1}'
            cur_sig = self.hdlmodule.signal(cur_name)
            slice_move = AHDL_MOVE(AHDL_VAR(cur_sig, Ctx.STORE),
                                   AHDL_VAR(prev_sig, Ctx.LOAD))
            guard = self.stages[num].block.codes[0]
            assert guard.is_a(AHDL_PIPELINE_GUARD)
            reg_slice_moves[id(guard)].append(slice_move)
        return reg_replace_table, reg_slice_moves


class AHDLRegisterSliceTransformer(AHDLTransformer):
    def __init__(self, replace_table:dict[tuple, tuple], slice_moves:dict[int, list], hdlmodule):
        self._replace_table = replace_table
        self._slice_moves = slice_moves
        self.hdlmodule = hdlmodule

    def visit_AHDL_VAR(self, ahdl):
        key = id(self.current_stm), ahdl.sig
        if key in self._replace_table:
            return AHDL_VAR(self._replace_table[key], ahdl.ctx)
        else:
            return ahdl

    def visit_AHDL_PIPELINE_GUARD(self, ahdl):
        if id(ahdl) in self._slice_moves:
            new_ahdl = super().visit_AHDL_PIPELINE_GUARD(ahdl)
            codes = new_ahdl.blocks[0].codes + tuple(self._slice_moves[id(ahdl)])
            return AHDL_PIPELINE_GUARD(new_ahdl.conds[0], codes)
        else:
            return super().visit_AHDL_PIPELINE_GUARD(ahdl)


class LoopPipelineBuilder(PipelineBuilder):
    def __init__(self, scope, stg, blk2states):
        super().__init__(scope, stg, blk2states)
        self.is_finite_loop = True

    def post_build(self, dfg, pstate_helper) -> AHDL_STM:
        cond_defs = self.scope.usedef.get_stms_defining(dfg.region.cond)
        assert len(cond_defs) == 1
        cond_def = list(cond_defs)[0]

        loop_cond = self.translator.visit(cond_def.src)

        for i, stage in enumerate(self.stages[:]):
            new_stage = self._add_last_signal_chain(pstate_helper, stage, loop_cond)
            if new_stage:
                self.stages[i] = new_stage

        # make the start condition of pipeline
        enable0 = pstate_helper.enable_signal(0)
        loop_enable = AHDL_ASSIGN(AHDL_VAR(enable0, Ctx.STORE),
                                  loop_cond)
        self.hdlmodule.add_static_assignment(loop_enable)
        # self.stages[0] = dataclasses.replace(self.stages[0], enable=loop_enable)

        exit_signal = pstate_helper.exit_signal(len(self.stages) - 1)
        last_stage = self.build_exit_detection_block(dfg, pstate_helper, exit_signal,
                                        cond_def, self.stages[-1])
        self.stages[-1] = last_stage

        exit_stm = self.build_exit_block(dfg, pstate_helper, exit_signal)
        return exit_stm

    def build_exit_detection_block(self, dfg, pstate_helper, exit_signal, cond_def:MOVE, last_stage:PipelineStage) -> PipelineStage:
        # make a condition for unexecutable loop
        loop_init = self.translator.visit(dfg.region.init)
        loop_cond = self.translator.visit(cond_def.src)
        assert loop_init and loop_cond
        args = []
        loop_cnt = self.translator._make_signal(self.hdlmodule, dfg.region.counter)
        for i, a in enumerate(loop_cond.args):
            if a.is_a(AHDL_VAR) and a.sig == loop_cnt:
                args.append(loop_init)
            else:
                args.append(a)
        assert loop_cond.is_a(AHDL_OP)
        loop_cond = AHDL_OP(loop_cond.op, *args)

        # make the exit condition of pipeline
        if last_stage.step > 0:
            last = pstate_helper.last_signal(last_stage.step - 1)
            ready = pstate_helper.ready_signal(last_stage.step)
            loop_end_cond1 = AHDL_OP('BitAnd',
                                     AHDL_VAR(last, Ctx.LOAD),
                                     AHDL_VAR(ready, Ctx.LOAD))
        else:
            last = pstate_helper.last_signal(last_stage.step)
            loop_end_cond1 = AHDL_VAR(last, Ctx.LOAD)
        loop_end_cond2 = AHDL_OP('Invert', loop_cond)
        loop_end_cond = AHDL_OP('Or', loop_end_cond1, loop_end_cond2)
        conds = tuple([loop_end_cond])
        codes = tuple([AHDL_MOVE(AHDL_VAR(exit_signal, Ctx.STORE), AHDL_CONST(1))])
        blocks = tuple([AHDL_BLOCK('', codes)])
        loop_end_stm = AHDL_IF(conds, blocks)
        return dataclasses.replace(last_stage, block=AHDL_BLOCK('', last_stage.block.codes + (loop_end_stm,)))

    def build_exit_block(self, dfg, pstate_helper, exit_signal) -> AHDL_STM:
        # if (exit)
        #    exit <= 0
        #    state <= loop_exit
        conds = [AHDL_VAR(exit_signal, Ctx.LOAD)]
        codes = []
        for i in range(len(self.stages)):
            if i == len(self.stages) - 1 and len(self.stages) > 1:
                break
            l = pstate_helper.last_signal(i)
            codes.append(AHDL_MOVE(AHDL_VAR(l, Ctx.STORE), AHDL_CONST(0)))

        state_reg_reset = AHDL_MOVE(AHDL_VAR(pstate_helper.substate_var, Ctx.STORE), AHDL_CONST(0))
        codes.append(state_reg_reset)

        assert len(dfg.region.exits) == 1
        codes.extend([
            AHDL_MOVE(AHDL_VAR(exit_signal, Ctx.STORE), AHDL_CONST(0)),
            AHDL_TRANSITION(dfg.region.exits[0].name)
        ])
        blocks = [AHDL_BLOCK('', tuple(codes))]
        pipe_end_stm = AHDL_TRANSITION_IF(tuple(conds), tuple(blocks))
        return pipe_end_stm

    def _build_scheduled_items(self, dfg):
        nodes = []
        for n in dfg.get_scheduled_nodes():
            if n.begin < 0:
                continue
            if n.tag.is_a(CJUMP):
                # remove cjump for the loop
                sym = qualified_symbols(n.tag.exp, self.scope)[-1]
                if sym is dfg.region.cond:
                    continue
                else:
                    assert False
            nodes.append(n)
        super()._build_scheduled_items(nodes)

    def _add_last_signal_chain(self, pstate_helper, stage, cond) -> PipelineStage|None:
        is_last = stage.step == len(self.stages) - 1
        last = pstate_helper.last_signal(stage.step)
        l_lhs = AHDL_VAR(last, Ctx.STORE)
        if stage.step == 0:
            ready = pstate_helper.ready_signal(stage.step)
            l_rhs = AHDL_OP('Invert', cond)
        elif not is_last:
            prev_last = AHDL_VAR(pstate_helper.last_signal(stage.step - 1), Ctx.LOAD)
            ready = AHDL_VAR(pstate_helper.ready_signal(stage.step), Ctx.LOAD)
            l_rhs = AHDL_OP('BitAnd', prev_last, ready)
        else:
            return None
        set_last = AHDL_MOVE(l_lhs, l_rhs)
        return dataclasses.replace(stage, block=AHDL_BLOCK('', stage.block.codes + (set_last,)))

    def _add_control_chain_no_stall(self, pstate_helper, stage) -> PipelineStage:
        if stage.step == 0:
            v_now = pstate_helper.valid_signal(stage.step)
            if stage.has_enable:
                v_prev = pstate_helper.enable_signal(stage.step)
            else:
                v_prev = None
        else:
            v_now = pstate_helper.valid_signal(stage.step)
            v_prev = pstate_helper.valid_signal(stage.step - 1)
        is_last = stage.step == len(self.stages) - 1

        r_now = pstate_helper.ready_signal(stage.step)
        if not is_last:
            r_next = AHDL_VAR(pstate_helper.ready_signal(stage.step + 1), Ctx.LOAD)
        else:
            r_next = AHDL_CONST(1)
        if stage.has_enable:
            en = AHDL_VAR(pstate_helper.enable_signal(stage.step), Ctx.LOAD)
            ready_rhs = AHDL_OP('BitAnd', r_next, en)
        else:
            ready_rhs = r_next
        ready_stm = AHDL_MOVE(AHDL_VAR(r_now, Ctx.STORE), ready_rhs)

        result_codes = []
        result_codes.append(ready_stm)

        if not is_last:
            rhs = AHDL_VAR(v_prev, Ctx.LOAD)
            set_valid = AHDL_MOVE(AHDL_VAR(v_now, Ctx.STORE), rhs)
            result_codes.append(set_valid)
        return dataclasses.replace(stage, block=AHDL_BLOCK('', stage.block.codes + tuple(result_codes)))


class WorkerPipelineBuilder(PipelineBuilder):
    def __init__(self, scope, stg, blk2states):
        super().__init__(scope, stg, blk2states)
        self.is_finite_loop = False

    def _build_scheduled_items(self, dfg):
        nodes = []
        for n in dfg.get_scheduled_nodes():
            if n.begin < 0:
                continue
            nodes.append(n)
        super()._build_scheduled_items(nodes)
