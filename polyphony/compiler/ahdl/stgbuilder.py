import sys
from collections import OrderedDict, defaultdict
import dataclasses
import functools
from .ahdl import *
from .hdlmodule import HDLModule
from .stg import STG
from ..common.env import env
from ..ir.block import Block
from ..ir.ir import *
from ..ir.irhelper import qualified_symbols, irexp_type
from ..ir.irvisitor import IRVisitor
from ..ir.types.type import Type
from logging import getLogger
logger = getLogger(__name__)


class ScheduledItemQueue(object):
    def __init__(self):
        self.queue = defaultdict(list)

    def push(self, sched_time, item, tag):
        if sched_time == -1:
            self.queue[sys.maxsize].append((item, tag))
        else:
            self.queue[sched_time].append((item, tag))

    def peek(self, sched_time):
        return self.queue[sched_time]

    def pop(self):
        for sched_time, items in sorted(self.queue.items()):
            yield (sched_time, items)


class STGBuilder(object):
    def __init__(self):
        self.dfg2stg = {}
        self.blk2states: dict[str, list[State]] = {}

    def process(self, hdlmodule):
        self.hdlmodule = hdlmodule
        self.blk2states = {}
        if hdlmodule.scope.is_module():
            ctor = hdlmodule.scope.find_ctor()
            stgs = self._process_scope(ctor)
            fsm_name = stgs[0].name
            self.hdlmodule.add_fsm(fsm_name, ctor)
            self.hdlmodule.add_fsm_stg(fsm_name, stgs)

            for w in hdlmodule.scope.workers:
                stgs = self._process_scope(w)
                fsm_name = w.base_name
                self.hdlmodule.add_fsm(fsm_name, w)
                self.hdlmodule.add_fsm_stg(fsm_name, stgs)
        else:
            stgs = self._process_scope(hdlmodule.scope)
            fsm_name = stgs[0].name
            self.hdlmodule.add_fsm(fsm_name, hdlmodule.scope)
            self.hdlmodule.add_fsm_stg(fsm_name, stgs)

    def _process_scope(self, scope):
        self.scope = scope
        stgs = []
        dfgs = scope.dfgs(bottom_up=False)
        for i, dfg in enumerate(dfgs):
            stg = self._process_dfg(i, dfg)
            stgs.append(stg)
            self.dfg2stg[dfg] = stg

        main_stg = stgs[0]
        s1 = main_stg.states[0]
        for s2 in main_stg.states[1:]:
            self._resolve_transition(s1, s2, self.blk2states)
            s1 = s2
        # functools.reduce(lambda s1, s2: self._resolve_transition(s1, s2, self.blk2states), main_stg.states)
        if scope.is_worker() or scope.is_testbench():
            self._resolve_transition(main_stg.states[-1], main_stg.states[-1], self.blk2states)
        else:
            self._resolve_transition(main_stg.states[-1], main_stg.states[0], self.blk2states)

        for stg in stgs[1:]:
            s1 = stg.states[0]
            for s2 in stg.states[1:]:
                self._resolve_transition(s1, s2, self.blk2states)
                s1 = s2
            # functools.reduce(lambda s1, s2: s1.resolve_transition(s2, self.blk2states), stg.states)
            self._resolve_transition(stg.states[-1], stg.states[0], self.blk2states)

        return stgs

    def _resolve_transition(self, state, next_state, blk2states: dict[str, list[State]]):
        code = state.block.codes[-1]
        if code.is_a(AHDL_TRANSITION):
            transition = cast(AHDL_TRANSITION, code)
            if transition.is_empty():
                target_state = next_state
            else:
                # assert isinstance(transition.target_name, Block)
                assert isinstance(transition.target_name, str)
                target_state = blk2states[transition.target_name][0]
            transition.update_target(target_state.name)
        elif code.is_a(AHDL_TRANSITION_IF):
            for i, ahdlblk in enumerate(code.blocks):
                # assert len(ahdlblk.codes) == 1
                assert ahdlblk.codes[-1].is_a(AHDL_TRANSITION)
                transition = cast(AHDL_TRANSITION, ahdlblk.codes[-1])
                assert isinstance(transition.target_name, str)
                target_state = blk2states[transition.target_name][0]
                transition.update_target(target_state.name)
        return next_state


    def _get_parent_stg(self, dfg):
        return self.dfg2stg[dfg.parent]

    def _process_dfg(self, index, dfg):
        from .stg_pipeline import LoopPipelineBuilder, WorkerPipelineBuilder

        is_main = index == 0
        if is_main:
            stg_name = self.scope.base_name
        else:
            stg_name = f'{self.scope.base_name}_L{index}'
        if self.scope.is_method():
            stg_name = self.scope.parent.base_name + '_' + stg_name

        parent_stg = self._get_parent_stg(dfg) if not is_main else None
        stg = STG(stg_name, parent_stg, self.hdlmodule)
        stg.scheduling = dfg.synth_params['scheduling']
        if stg.scheduling == 'pipeline':
            if not is_main:
                if self.scope.is_worker() and not dfg.region.counter:
                    builder = WorkerPipelineBuilder(self.scope, stg, self.blk2states)
                else:
                    builder = LoopPipelineBuilder(self.scope, stg, self.blk2states)
            else:
                raise NotImplementedError()
        else:
            builder = StateBuilder(self.scope, stg, self.blk2states)
        builder.build(dfg, is_main)
        return stg


class STGItemBuilder(object):
    def __init__(self, scope, stg, blk2states: dict[str, list[State]]):
        self.scope = scope
        self.hdlmodule = env.hdlscope(scope)
        self.stg = stg
        self.blk2states: dict[str, list[State]] = blk2states
        self.translator = AHDLTranslator(stg.name, self, scope)

    def _get_block_nodes_map(self, dfg):
        blk_nodes_map = defaultdict(list)
        for n in dfg.get_scheduled_nodes():
            if n.begin < 0:
                continue
            blk = n.tag.block
            blk_nodes_map[blk].append(n)
        return blk_nodes_map

    def _build_scheduled_items(self, nodes):
        scheduled_node_map = OrderedDict()
        for n in nodes:
            if n.begin not in scheduled_node_map:
                scheduled_node_map[n.begin] = []
            scheduled_node_map[n.begin].append(n)

        last_step = 0
        scheduled_node_list = []
        for step, nodes in scheduled_node_map.items():
            delta = step - last_step
            last_step = step
            scheduled_node_list.append((delta, nodes))
        cur_sched_time = 0
        self.translator.scheduled_items = self.scheduled_items
        for delta, nodes in scheduled_node_list:
            cur_sched_time += delta
            self.translator.set_sched_time(cur_sched_time)
            for node in nodes:
                if node.priority < 0:
                    continue
                self.translator.process_node(node)

    def _new_state(self, name, step, codes):
        return self.stg.new_state(name, AHDL_BLOCK(name, tuple(codes)), step)


class StateBuilder(STGItemBuilder):
    def __init__(self, scope, stg, blk2states: dict[str, list[State]]):
        super().__init__(scope, stg, blk2states)

    def build(self, dfg, is_main):
        blk_nodes_map = self._get_block_nodes_map(dfg)
        for i, blk in enumerate(sorted(dfg.region.blocks())):
            self.scheduled_items = ScheduledItemQueue()
            if blk in blk_nodes_map:
                nodes = blk_nodes_map[blk]
                self._build_scheduled_items(nodes)

            blk_name = blk.nametag + str(blk.num)
            prefix = self.stg.name + '_' + blk_name
            logger.debug('# BLOCK ' + prefix + ' #')

            is_first = True if i == 0 else False
            is_last = True if i == len(dfg.region.blocks()) - 1 else False
            states = self._build_states_for_block(prefix, blk, is_main, is_first, is_last)

            assert states
            self.stg.add_states(states)
            self.blk2states[blk.name] = states

    def _build_states_for_block(self, state_prefix, blk, is_main, is_first, is_last) -> list[State]:
        states = []
        for step, items in self.scheduled_items.pop():
            codes = []
            for item, _ in items:
                if isinstance(item, AHDL):
                    codes.append(item)
                else:
                    assert False
            if not codes[-1].is_a([AHDL_TRANSITION, AHDL_TRANSITION_IF]):
                codes.append(AHDL_TRANSITION(''))
            name = f'{state_prefix}_S{step}'
            state = self._new_state(name, step + 1, codes)
            states.append(state)
        if not states:
            name = f'{state_prefix}_S0'
            codes = [AHDL_TRANSITION('')]
            states = [self._new_state(name, 1, codes)]

        if blk.stms and blk.stms[-1].is_a(JUMP):
            jump = blk.stms[-1]
            last_state = states[-1]
            trans = last_state.block.codes[-1]
            assert trans.is_a([AHDL_TRANSITION])
            if trans.is_a(AHDL_TRANSITION):
                trans.update_target(jump.target.name)

        # deal with the first/last state
        if not is_main:
            pass
        elif self.scope.is_worker() or self.scope.is_testbench():
            if is_first:
                init_state = states[0]
                assert init_state.block.codes[-1].is_a([AHDL_TRANSITION, AHDL_TRANSITION_IF])
                name = f'{state_prefix}_INIT'
                states[0] = dataclasses.replace(init_state, name=name)
            if is_last:
                last_state = states[-1]
                if self.scope.is_loop_worker():
                    codes = [AHDL_TRANSITION(self.scope.entry_block.name)]
                elif self.scope.is_worker():
                    codes = [AHDL_TRANSITION('')]
                elif self.scope.is_testbench():
                    # FIXME: Avoid dependence on verilog
                    codes = [
                        AHDL_INLINE('$display("%5t:finish", $time);'),
                        AHDL_INLINE('$finish();')
                    ]
                else:
                    assert False
                finish_state = self._new_state(f'{state_prefix}_FINISH',
                                               last_state.step + 1,
                                               codes)
                states.append(finish_state)
        else:
            if is_first:
                first_state = states[0]
                block = first_state.block
                assert block.codes[-1].is_a([AHDL_TRANSITION, AHDL_TRANSITION_IF])
                prolog = AHDL_SEQ(AHDL_CALLEE_PROLOG(self.stg.name), 0, 1)
                codes = (prolog,) + block.codes
                name = f'{state_prefix}_INIT'
                new_block = AHDL_BLOCK(name, tuple(codes))
                states[0] = dataclasses.replace(first_state, name=name, block=new_block)
            if is_last:
                name = f'{state_prefix}_FINISH'
                finish_state = states[-1]
                block = finish_state.block
                assert block.codes[-1].is_a(AHDL_TRANSITION)
                epilog = AHDL_SEQ(AHDL_CALLEE_EPILOG(self.stg.name), 0, 1)
                new_block = AHDL_BLOCK(name, block.codes[:-1] + (epilog,) + (block.codes[-1],))
                states[-1] = dataclasses.replace(finish_state, name=name, block=new_block)
        return states


def _signal_width(sym) -> int | tuple[int]:
    width = -1
    if sym.typ.is_seq():
        width = (sym.typ.element.width, sym.typ.length)
    elif sym.typ.is_int():
        width = sym.typ.width
    elif sym.typ.is_bool():
        width = 1
    elif sym.typ.is_port():
        if sym.typ.dtype.is_int() or sym.typ.dtype.is_bool():
            width = sym.typ.dtype.width
        else:
            raise NotImplementedError()
    elif sym.typ.is_object():
        # The signal indicating an object is
        # represented by an int value to identify the object.
        width = env.config.default_int_width
    elif sym.is_condition():
        width = 1
    return width


def _tags_from_sym(sym) -> set[str]:
    tags = set()
    if sym.typ.is_int():
        if sym.typ.signed:
            tags.add('int')
        if sym.is_alias():
            tags.add('net')
        else:
            tags.add('reg')
    elif sym.typ.is_bool():
        if sym.is_alias():
            tags.add('net')
        else:
            tags.add('reg')
    elif sym.typ.is_tuple():
        elm_t = sym.typ.element
        if elm_t.is_int() and elm_t.signed:
            tags.add('int')
        if sym.scope.is_containable():
            tags.add('rom')
        elif sym.is_alias():
            tags.add('netarray')
        else:
            tags.add('regarray')
    elif sym.typ.is_list():
        elm_t = sym.typ.element
        if elm_t.is_int() and elm_t.signed:
            tags.add('int')
        if sym.typ.ro and sym.scope.is_containable():
            tags.add('rom')
        else:
            tags.add('regarray')
    elif sym.typ.is_port():
        di = sym.typ.direction
        assert di != '?'
        if di != 'inout':
            tags.add(di)
        tags.add('single_port')

        root_sym = sym.typ.root_symbol
        dtype = sym.typ.dtype
        width = dtype.width
        port_scope = sym.typ.scope
        direction = root_sym.typ.direction
        assert direction != '?'
        assigned = root_sym.typ.assigned
        assert port_scope.base_name.startswith('Port')
        if dtype.signed:
            tags.add('int')
        if direction == 'input' or assigned:
            tags.add('net')
        else:
            tags.add('reg')
    elif sym.typ.is_object():
        sym_scope = sym.typ.scope
        if sym_scope.orig_name == 'polyphony.Reg':
            assert not sym.is_alias()
            tags.add('reg')
        elif sym_scope.orig_name == 'polyphony.Net':
            assert sym.is_alias()
            tags.add('net')
        elif sym.is_alias():
            tags.add('net')
        elif sym.is_self():
            tags.add('self')
        else:
            if sym.scope.is_testbench():
                tags.add('dut')
            else:
                tags.add('subscope')

    if sym.is_param() and sym.scope.is_function_module():
        tags.add('input')
        tags.remove('reg')
        tags.add('net')
    elif sym.is_return() and sym.scope.is_function_module():
        tags.add('output')
    elif sym.is_condition():
        tags.add('condition')

    if sym.is_induction():
        tags.add('induction')
    if sym.is_field():
        tags.add('field')
    if 'reg' in tags:
        tags.add('initializable')
    return tags


class AHDLTranslator(IRVisitor):
    def __init__(self, name, host, scope):
        super().__init__()
        self.name = name
        self.host = host
        self.scope = scope
        self.hdlmodule = env.hdlscope(scope)
        self.scheduled_items = None

    def process_node(self, node):
        self.node = node
        self.visit(node.tag)

    def set_sched_time(self, sched_time):
        self.sched_time = sched_time

    def get_signal_prefix(self, ir):
        assert ir.is_a(CALL)
        callee_scope = ir.get_callee_scope(self.scope)
        if callee_scope.is_class():
            assert isinstance(self.current_stm, MOVE)
            name = self.current_stm.dst.name
            return f'{name}_{env.ctor_name}'
        elif callee_scope.is_method():
            assert isinstance(ir.func, ATTR)
            instance_name = self.make_instance_name(ir.func)
            return f'{instance_name}_{ir.name}'
        else:
            name = callee_scope.base_name
            n = self.node.instance_num
            return f'{name}_{n}'

    def make_instance_name(self, ir):
        assert isinstance(ir, ATTR)

        def make_instance_name_rec(ir):
            assert isinstance(ir, ATTR)
            if isinstance(ir.exp, TEMP):
                exp_sym = qualified_symbols(ir.exp, self.scope)[-1]
                assert isinstance(exp_sym, Symbol)
                exp_typ = exp_sym.typ
                if ir.exp.name == env.self_name:
                    if self.scope.is_ctor():
                        return self.scope.parent.base_name
                    else:
                        return self.scope.base_name
                elif exp_typ.is_class():
                    return exp_typ.scope.base_name
                else:
                    return exp_sym.hdl_name()
            else:
                exp_name = make_instance_name_rec(ir.exp)
                attr_name = ir.exp.name
                instance_name = f'{exp_name}_{attr_name}'
            return instance_name
        return make_instance_name_rec(ir)

    def _emit(self, item, sched_time):
        logger.debug('emit ' + str(item) + ' at ' + str(sched_time))
        self.scheduled_items.push(sched_time, item, tag='')
        self.hdlmodule.ahdl2dfgnode[id(item)] = (item, self.node)

    def visit_UNOP(self, ir):
        exp = self.visit(ir.exp)
        return AHDL_OP(ir.op, exp)

    def visit_BINOP(self, ir):
        left = self.visit(ir.left)
        right = self.visit(ir.right)
        return AHDL_OP(ir.op, left, right)

    def visit_RELOP(self, ir):
        left = self.visit(ir.left)
        right = self.visit(ir.right)
        return AHDL_OP(ir.op, left, right)

    def visit_CONDOP(self, ir):
        cond = self.visit(ir.cond)
        left = self.visit(ir.left)
        right = self.visit(ir.right)
        return AHDL_IF_EXP(cond, left, right)

    def _visit_args(self, ir):
        callargs = []
        for i, (_, arg) in enumerate(ir.args):
            a = self.visit(arg)
            callargs.append(a)
        return callargs

    def visit_CALL(self, ir):
        callee_scope = ir.get_callee_scope(self.scope)
        if callee_scope.is_method():
            instance_name = self.make_instance_name(ir.func)
        else:
            qname = callee_scope.qualified_name()
            n = self.node.instance_num
            instance_name = f'{qname}_{n}'
        signal_prefix = self.get_signal_prefix(ir)
        callargs = self._visit_args(ir)
        if not callee_scope.is_method():
            sym = qualified_symbols(ir.func, self.scope)[-1]
            assert isinstance(sym, Symbol)
            tags = {'dut'}
            width = -1
            sig = self.hdlmodule.gen_sig(instance_name, width, tags, sym)
            assert isinstance(sig, Signal)
            self.hdlmodule.add_subscope(sig, env.hdlscope(callee_scope))

        ahdl_call = AHDL_MODULECALL(callee_scope, tuple(callargs), instance_name, signal_prefix, tuple())
        return ahdl_call

    def visit_NEW(self, ir):
        callee_scope = ir.get_callee_scope(self.scope)
        if callee_scope.is_module():
            assert len(ir.args) == 0
            assert isinstance(self.current_stm, MOVE)
            dst_sym = qualified_symbols(self.current_stm.dst, self.scope)[-1]
            assert isinstance(dst_sym, Symbol)
            sig = self._make_signal(self.hdlmodule, dst_sym)
            self.hdlmodule.add_subscope(sig, env.hdlscope(callee_scope))
        else:
            assert False, 'It must be inlined'

    def translate_builtin_len(self, syscall):
        _, mem = syscall.args[0]
        assert mem.is_a(TEMP)
        mem_typ = irexp_type(mem, self.scope)
        assert mem_typ.is_seq()
        assert isinstance(mem_typ.length, int)
        return AHDL_CONST(mem_typ.length)

    def visit_SYSCALL(self, ir):
        name = ir.name
        logger.debug(name)
        if name == 'print':
            fname = '!hdl_print'
        elif name == 'assert':
            fname = '!hdl_assert'
        elif name == 'polyphony.verilog.display':
            fname = '!hdl_verilog_display'
        elif name == 'polyphony.verilog.write':
            fname = '!hdl_verilog_write'
        elif name == 'len':
            return self.translate_builtin_len(ir)
        elif name == '$new':
            dst_sym = qualified_symbols(self.current_stm.dst, self.scope)[-1]
            return AHDL_CONST(dst_sym.id)
        elif name == 'polyphony.timing.clksleep':
            _, cycle = ir.args[0]
            # If sleep time is less than thredhold, simply generate an empty state
            if cycle.is_a(CONST) and cycle.value <= env.sleep_sentinel_thredhold:
                for i in range(cycle.value):
                    self._emit(AHDL_NOP('wait a cycle'), self.sched_time + i)
                return
            # Sleep time is variable or greater than thredhold,
            # so sleep_sentinel is used to perform wait processing.
            cn = self.visit(cycle)
            clkvar = AHDL_VAR(self.hdlmodule.get_clock_signal(), Ctx.LOAD)
            start = AHDL_MOVE(AHDL_VAR(self.hdlmodule.get_sleep_sentinel_signal(), Ctx.STORE), clkvar)
            args = ('GtE',
                    AHDL_OP('Add',
                            AHDL_VAR(self.hdlmodule.get_sleep_sentinel_signal(), Ctx.LOAD),
                            cn),
                    clkvar,
                    )
            self._emit(start, self.sched_time)
            self._emit(AHDL_META_WAIT('WAIT_COND', *args), self.sched_time + 1)
            return
        elif name == 'polyphony.timing.clktime':
            return AHDL_VAR(self.hdlmodule.get_clock_signal(), Ctx.LOAD)
        elif name in ('polyphony.timing.wait_rising',
                      'polyphony.timing.wait_falling',
                      'polyphony.timing.wait_edge',
                      'polyphony.timing.wait_value'):
            assert False, 'It must be inlined'
        elif name == 'polyphony.timing.wait_until':
            scope_name = ir.args[0][1]
            scope_sym = qualified_symbols(scope_name, self.scope)[-1]
            assert scope_sym.typ.is_function()
            pred = scope_sym.typ.scope
            #assert pred.is_assigned()
            translator = AHDLCombTranslator(self.hdlmodule)
            translator.process(pred)
            for assign in translator.codes:
                self.hdlmodule.add_static_assignment(assign)
            args = ('NotEq', AHDL_CONST(0), translator.return_var)
            self._emit(AHDL_META_WAIT('WAIT_COND', *args),
                       self.sched_time)
            return
        else:
            # TODO: user-defined builtins
            return
        args = tuple([self.visit(arg) for _, arg in ir.args])
        return AHDL_PROCCALL(fname, args)

    def visit_CONST(self, ir):
        if ir.value is None:
            return AHDL_SYMBOL("'bz")
        elif isinstance(ir.value, bool):
            return AHDL_CONST(int(ir.value))
        else:
            return AHDL_CONST(ir.value)

    def visit_MREF(self, ir):
        offset = self.visit(ir.offset)
        memvar = self.visit(ir.mem)
        mem_sym = qualified_symbols(ir.mem, self.scope)[-1]
        assert isinstance(mem_sym, Symbol)
        typ = mem_sym.typ
        # Only static class or global field can be hdl function
        if mem_sym.scope.is_containable() and (typ.is_tuple() or typ.is_list() and typ.ro):
            return AHDL_FUNCALL(memvar, (offset, ))
        else:
            return AHDL_SUBSCRIPT(memvar, offset)

    def visit_MSTORE(self, ir):
        offset = cast(AHDL_EXP, self.visit(ir.offset))
        exp = cast(AHDL_EXP, self.visit(ir.exp))
        memvar = cast(AHDL_MEMVAR, self.visit(ir.mem))
        assert memvar.is_a(AHDL_MEMVAR)
        memvar = AHDL_MEMVAR(memvar.vars, ctx=Ctx.STORE)
        dst = AHDL_SUBSCRIPT(memvar, offset)
        return AHDL_MOVE(dst, exp)

    def _build_mem_initialize_seq(self, array, memvar):
        for i, item in enumerate(array.items):
            if not(isinstance(item, CONST) and item.value is None):
                idx = AHDL_CONST(i)
                # memvar = AHDL_MEMVAR(sig, Ctx.STORE)
                ahdl_item = self.visit(item)
                ahdl_move = AHDL_MOVE(AHDL_SUBSCRIPT(memvar, idx), ahdl_item)
                self._emit(ahdl_move, self.sched_time)

    def visit_ARRAY(self, ir):
        # array expansion
        assert ir.repeat.is_a(CONST)
        ir.items = [item.clone() for item in ir.items * ir.repeat.value]

        assert isinstance(self.current_stm, MOVE)
        sym = qualified_symbols(self.current_stm.dst, self.scope)[-1]
        assert isinstance(sym, Symbol)
        if sym.scope.is_containable() and (sym.typ.is_tuple() or sym.typ.is_list() and sym.typ.ro):
            # this array will be rom
            pass
        else:
            ahdl_memvar = self.visit(self.current_stm.dst)
            self._build_mem_initialize_seq(ir, ahdl_memvar)

    def visit_TEMP(self, ir):
        sym = self.scope.find_sym(ir.name)
        assert sym
        sig = self._make_signal(self.hdlmodule, sym)
        if sym.typ.is_seq():
            return AHDL_MEMVAR(sig, ir.ctx)
        else:
            return AHDL_VAR(sig, ir.ctx)

    def visit_ATTR(self, ir):
        qsym = qualified_symbols(ir, self.scope)  # ir.qualified_symbol
        sigs = []
        for sym in qsym:
            if sym.is_self():
                continue
            hdlscope = env.hdlscope(sym.scope)
            assert hdlscope
            sig = self._make_signal(hdlscope, sym)
            sigs.append(sig)
        if qsym[-1].typ.is_seq():
            ahdl = AHDL_MEMVAR(tuple(sigs), ir.ctx)
        else:
            ahdl = AHDL_VAR(tuple(sigs), ir.ctx)
        return ahdl

    def _make_signal(self, hdlscope, sym) -> Signal:
        tags = _tags_from_sym(sym)
        width = _signal_width(sym)
        sig_name = self._make_signal_name(sym, tags)
        sig = hdlscope.signal(sig_name)
        if sig:
            return sig
        sig = hdlscope.gen_sig(sig_name, width, tags, sym)
        # TODO: remove this
        if sig.is_subscope() or sig.is_dut():
            hdlscope.add_subscope(sig, env.hdlscope(sym.typ.scope))
        if sig.is_single_port() and sig.is_initializable():
            assert sym.typ.is_port()
            if isinstance(sym.typ.init, bool):
                sig.init_value = 1 if sym.typ.init else 0
            else:
                sig.init_value = sym.typ.init
        return sig

    def _make_signal_name(self, sym, tags) -> str:
        if sym.scope is not self.scope:
            sig_name = sym.hdl_name()
        elif self.scope.is_worker() or self.scope.is_method():
            is_param = False
            if self.scope.is_ctor() and self.scope.parent.is_module() and self.scope.parent.module_params:
                is_param = any([sym is s for s, _ in self.scope.parent.module_params])
            if is_param:
                sig_name = sym.hdl_name()[len(Symbol.param_prefix):]
                tags.update({'parameter'})
                if 'reg' in tags:
                    tags.remove('reg')
            else:
                # sig_name = f'{self.scope.base_name}_{sym.hdl_name()}'
                sig_name = f'{sym.hdl_name()}_{sym.id}'
        elif sym.is_param():
            sig_name = f'{self.scope.base_name}_{sym.hdl_name()}'
        elif sym.is_return():
            sig_name = f'{self.scope.base_name}_out_0'
        elif sym.scope.is_closure():
            sig_name = f'{sym.hdl_name()}_{sym.id}'
        else:
            sig_name = sym.hdl_name()
        return sig_name

    def visit_EXPR(self, ir):
        if not (ir.exp.is_a([CALL, SYSCALL, MSTORE])):
            return

        if self._is_port_method(ir.exp):
            return self._make_port_access(ir.exp, None)
        elif self._is_module_method(ir.exp):
            return
        if ir.exp.is_a(CALL):
            self._call_proc(ir)
        else:
            exp = self.visit(ir.exp)
            if exp:
                self._emit(exp, self.sched_time)

    def visit_CJUMP(self, ir):
        cond = self.visit(ir.exp)
        if cond.is_a(AHDL_CONST) and cond.value == 1:
            self._emit(AHDL_TRANSITION(ir.true.name), self.sched_time)
        else:
            conds = (cond, AHDL_CONST(1))
            blocks = (AHDL_BLOCK('', (AHDL_TRANSITION(ir.true.name),)),
                      AHDL_BLOCK('', (AHDL_TRANSITION(ir.false.name),)))
            self._emit(AHDL_TRANSITION_IF(conds, blocks), self.sched_time)

    def visit_JUMP(self, ir):
        self._emit(AHDL_TRANSITION(ir.target.name), self.sched_time)

    def visit_MCJUMP(self, ir):
        for c, target in zip(ir.conds[:-1], ir.targets[:-1]):
            if c.is_a(CONST) and c.value == 1:
                cond = self.visit(c)
                self._emit(AHDL_TRANSITION(target.name), self.sched_time)
                return

        cond_list = []
        blocks = []
        for c, target in zip(ir.conds, ir.targets):
            cond = self.visit(c)
            cond_list.append(cond)
            blocks.append(AHDL_BLOCK('', (AHDL_TRANSITION(target.name),)))
        self._emit(AHDL_TRANSITION_IF(tuple(cond_list), tuple(blocks)), self.sched_time)

    def visit_RET(self, ir):
        pass

    def _call_proc(self, ir):
        if ir.is_a(MOVE):
            call = ir.src
        elif ir.is_a(EXPR):
            call = ir.exp

        ahdl_call = self.visit(call)
        if call.is_a(CALL) and ir.is_a(MOVE):
            dst = self.visit(ir.dst)
        else:
            dst = None
        if ir.is_a(MOVE) and ir.src.is_a([NEW, CALL]):
            callee_scope = ir.src.get_callee_scope(self.scope)
            if callee_scope.is_module():
                return
        self._emit_call_sequence(ahdl_call, dst, self.sched_time)

    def visit_MOVE(self, ir):
        if ir.src.is_a([CALL, NEW]):
            if self._is_port_method(ir.src):
                return self._make_port_access(ir.src, ir.dst)
            elif self._is_port_ctor(ir.src):
                return self._make_port_init(ir.src, ir.dst)
            elif self._is_net_ctor(ir.src):
                return self._make_net_init(ir.src, ir.dst)
            elif self._is_net_method(ir.src):
                return self._make_net_access(ir.src, ir.dst)
            elif self._is_module_method(ir.src):
                return
            self._call_proc(ir)
            return
        elif ir.src.is_a(TEMP) and (sym := self.scope.find_sym(ir.src.name)) and sym.is_param():
            if ir.src.name.endswith(env.self_name):
                return
            elif sym.typ.is_object() and sym.typ.scope.is_module():
                return
            elif sym.typ.is_port():
                return
        elif ir.src.is_a(IRVariable) and (sym := qualified_symbols(ir.src, self.scope)[-1]) and sym.typ.is_port():
            return
        src = self.visit(ir.src)
        dst = self.visit(ir.dst)
        if not src:
            return
        elif src.is_a(AHDL_VAR) and dst.is_a(AHDL_VAR) and src.sig == dst.sig:
            return
        elif dst.is_a(AHDL_MEMVAR) and src.is_a(AHDL_MEMVAR):
            src_sym = qualified_symbols(ir.src, self.scope)[-1]
            if src_sym.is_param():
                width = src_sym.typ.element.width
                length = src_sym.typ.length
                for i in range(length):
                    src_name = f'{src.sig.name}{i}'
                    self._emit(AHDL_MOVE(AHDL_SUBSCRIPT(dst, AHDL_CONST(i)),
                                         AHDL_SYMBOL(src_name)),
                               self.sched_time)

                mem = AHDL_MEMVAR(dst.sig, Ctx.LOAD)
                for i in range(length):
                    sig_name = f'{self.hdlmodule.name}_out_{dst.sig.name}{i}'
                    dst_sig = self.hdlmodule.gen_sig(sig_name, width)
                    dst_var = AHDL_VAR(dst_sig, Ctx.LOAD)
                    ahdl_assign = AHDL_ASSIGN(dst_var, AHDL_SUBSCRIPT(mem, AHDL_CONST(i)))
                    self.hdlmodule.add_static_assignment(ahdl_assign)

                return
        elif dst.is_a(AHDL_VAR) and self.scope.is_ctor() and dst.sig.is_initializable():
            # assert False
            dst.sig.init_value = src.value
        self._emit(AHDL_MOVE(dst, src), self.sched_time)

    def visit_PHI(self, ir):
        assert ir.ps and len(ir.args) == len(ir.ps) and len(ir.args) > 1
        ahdl_dst, if_exp = self._make_scalar_mux(ir)
        self._emit(AHDL_MOVE(ahdl_dst, if_exp), self.sched_time)

    def _emit_call_sequence(self, ahdl_call, dst, sched_time):
        assert ahdl_call.is_a(AHDL_MODULECALL)
        returns = []
        for arg in ahdl_call.args:
            if arg.is_a(AHDL_MEMVAR):
                returns.append(arg)
        # TODO:
        if dst:
            returns.append(dst)
        new_call = AHDL_MODULECALL(ahdl_call.scope, ahdl_call.args, ahdl_call.instance_name, ahdl_call.prefix, tuple(returns))
        step_n = self.node.latency()
        for i in range(step_n):
            self._emit(AHDL_SEQ(new_call, i, step_n), sched_time + i)

    def _make_scalar_mux(self, ir):
        ahdl_dst = self.visit(ir.var)
        arg_p = list(zip(ir.args, ir.ps))
        rexp, cond = arg_p[-1]
        cond = self.visit(cond)
        if cond.is_a(CONST) and cond.value:
            rexp = self.visit(rexp)
        else:
            signed = False
            # if rexp.is_a((TEMP, ATTR)) and rexp.symbol.typ.is_int():
            #     signed = rexp.symbol.typ.signed
            lexp = self.visit(rexp)
            # FIXME: do not depends verilog
            other = AHDL_SYMBOL("$signed('bz)") if signed else AHDL_SYMBOL("'bz")
            rexp = AHDL_IF_EXP(cond, lexp, other)
        for arg, p in arg_p[-2::-1]:
            lexp = self.visit(arg)
            cond = self.visit(p)
            if_exp = AHDL_IF_EXP(cond, lexp, rexp)
            rexp = if_exp
        return ahdl_dst, if_exp

    def visit_UPHI(self, ir):
        self.visit_PHI(ir)

    def visit_LPHI(self, ir):
        self.visit_PHI(ir)

    def _hooked_emit(self, ahdl, sched_time):
        self.hooked.append((ahdl, sched_time))

    def visit_CEXPR(self, ir):
        orig_emit_func = self._emit
        self._emit = self._hooked_emit
        self.hooked = []
        self.visit_EXPR(ir)
        self._emit = orig_emit_func
        for ahdl, sched_time in self.hooked:
            cond = self.visit(ir.cond)
            self._emit(AHDL_IF((cond,), (AHDL_BLOCK('', (ahdl,)),)), sched_time)

    def visit_CMOVE(self, ir):
        orig_emit_func = self._emit
        self._emit = self._hooked_emit
        self.hooked = []
        self.visit_MOVE(ir)
        self._emit = orig_emit_func
        for ahdl, sched_time in self.hooked:
            cond = self.visit(ir.cond)
            self._emit(AHDL_IF((cond,), (AHDL_BLOCK('', (ahdl,)),)), sched_time)

    def _is_port_method(self, ir):
        if not ir.is_a(CALL):
            return False
        callee_scope = ir.get_callee_scope(self.scope)
        return callee_scope.is_method() and callee_scope.parent.is_port()

    def _is_net_method(self, ir):
        if not ir.is_a(CALL):
            return False
        callee_scope = ir.get_callee_scope(self.scope)
        return callee_scope.is_method() and callee_scope.parent.name.startswith('polyphony.Net')

    def _is_port_ctor(self, ir):
        if not ir.is_a(NEW):
            return False
        callee_scope = ir.get_callee_scope(self.scope)
        return callee_scope.is_port()

    def _is_net_ctor(self, ir):
        if not ir.is_a(NEW):
            return False
        callee_scope = ir.get_callee_scope(self.scope)
        return callee_scope.name.startswith('polyphony.Net')

    def _make_port_access(self, call, target):
        assert isinstance(call.func, ATTR)
        port_var = cast(AHDL_VAR, self.visit(call.func.exp))
        callee_scope = call.get_callee_scope(self.scope)
        if callee_scope.base_name == 'wr':
            self._make_port_write_seq(call, port_var)
        elif callee_scope.base_name == 'rd':
            self._make_port_read_seq(target, port_var)
        elif callee_scope.base_name == 'assign':
            arg_sym = qualified_symbols(call.args[0][1], self.scope)[-1]
            assert isinstance(arg_sym, Symbol)
            self._make_port_assign(arg_sym, port_var)
        elif callee_scope.base_name == 'edge':
            self._make_port_edge(target, port_var, call.args[0][1], call.args[1][1])
        else:
            assert False

    def _make_port_write_seq(self, call, port_var:AHDL_VAR):
        assert call.args
        _, val = call.args[0]
        src = self.visit(val)
        port_var = AHDL_VAR(port_var.vars, ctx=Ctx.STORE)
        iow = AHDL_IO_WRITE(port_var,
                            src,
                            port_var.sig.is_output())
        assert port_var.sig.is_single_port()
        self._emit(iow, self.sched_time)

    def _make_port_read_seq(self, target, port_var:AHDL_VAR):
        if target:
            dst = self.visit(target)
        else:
            dst = None
        port_var = AHDL_VAR(port_var.vars, ctx=Ctx.LOAD)
        ior = AHDL_IO_READ(port_var,
                           dst,
                           port_var.sig.is_input())
        assert port_var.sig.is_single_port()
        self._emit(ior, self.sched_time)

    def _make_port_assign(self, scope_sym, port_var:AHDL_VAR):
        assert scope_sym.typ.is_function()
        assigned = scope_sym.typ.scope
        assert assigned.is_assigned()
        translator = AHDLCombTranslator(self.hdlmodule)
        translator.process(assigned)
        for assign in translator.codes:
            self.hdlmodule.add_static_assignment(assign)
        port_var = AHDL_VAR(port_var.vars, ctx=Ctx.STORE)
        assign = AHDL_ASSIGN(port_var, translator.return_var)
        self.hdlmodule.add_static_assignment(assign)

    def _make_port_edge(self, target, port_var, old, new):
        dst = self.visit(target)
        assert isinstance(dst, AHDL_VAR)
        assert dst.sig.is_net()
        _old = self.visit(old)
        _new = self.visit(new)
        self.hdlmodule.add_edge_detector(port_var, _old, _new)
        detect_var_name = f'is_{port_var.hdl_name}_change_{_old}_to_{_new}'
        detect_var_sig = self.hdlmodule.gen_sig(detect_var_name, 1, {'net'})
        edge = AHDL_VAR(detect_var_sig, Ctx.LOAD)
        self._emit(AHDL_MOVE(dst, edge), self.sched_time)

    def _make_port_init(self, new, target):
        callee_scope = new.get_callee_scope(self.scope)
        assert callee_scope.is_port()
        target_sym = qualified_symbols(target, self.scope)[-1]
        assert isinstance(target_sym, Symbol)
        port = target_sym.typ
        assert port.is_port()
        # make port signal
        self.visit(target)

    def _is_module_method(self, ir):
        if not ir.is_a(CALL):
            return False
        callee_scope = ir.get_callee_scope(self.scope)
        return callee_scope.is_method() and callee_scope.parent.is_module()

    def _net_sig(self, net_qsym):
        net_sym = net_qsym[-1]
        net_prefixes = net_qsym

        if net_prefixes[0].name == env.self_name:
            net_prefixes = net_prefixes[1:]
        net_name = '_'.join([pfx.hdl_name() for pfx in net_prefixes])

        dtype = net_sym.typ.scope.type_args[0]
        width = dtype.width
        tags = {'net'}
        net_sig = env.hdlscope(net_sym.scope).signal(net_name)
        if net_sig:
            net_sig.tags.update(tags)
            return net_sig
        net_sig = self.hdlmodule.gen_sig(net_name, width, tags, net_sym)
        return net_sig

    def _make_net_init(self, new, target):
        qsym = qualified_symbols(target, self.scope)
        net_sig = self._net_sig(qsym)
        scope_sym = new.args[0][1].symbol
        assert scope_sym.typ.is_function()
        assigned = scope_sym.typ.scope
        assert assigned.is_assigned()
        translator = AHDLCombTranslator(self.hdlmodule)
        translator.process(assigned)
        for assign in translator.codes:
            self.hdlmodule.add_static_assignment(assign)
        assign = AHDL_ASSIGN(AHDL_VAR(net_sig, Ctx.STORE),
                             translator.return_var)
        self.hdlmodule.add_static_assignment(assign)

    def _make_net_access(self, call, target):
        assert isinstance(call.func, ATTR)
        qsym = qualified_symbols(call.func, self.scope)
        net_qsym = qsym[:-1]
        net_sig = self._net_sig(net_qsym)

        callee_scope = call.get_callee_scope(self.scope)
        if callee_scope.base_name == 'rd':
            self._make_net_read_seq(target, net_sig)
        elif callee_scope.base_name == 'assign':
            self._make_net_assign(call.args[0][1].symbol, net_sig)
        else:
            assert False

    def _make_net_read_seq(self, target, net_sig):
        if target:
            dst = self.visit(target)
            mv = AHDL_MOVE(dst, AHDL_VAR(net_sig, Ctx.LOAD))
            self._emit(mv, self.sched_time)

    def _make_net_assign(self, scope_sym, net_sig):
        assert scope_sym.typ.is_function()
        assigned = scope_sym.typ.scope
        assert assigned.is_assigned()
        translator = AHDLCombTranslator(self.hdlmodule)
        translator.process(assigned)
        for assign in translator.codes:
            self.hdlmodule.add_static_assignment(assign)
        assign = AHDL_ASSIGN(AHDL_VAR(net_sig, Ctx.STORE),
                             translator.return_var)
        self.hdlmodule.add_static_assignment(assign)
        assert net_sig.is_net()


class AHDLCombTranslator(AHDLTranslator):
    def __init__(self, hdlmodule):
        self.hdlmodule = hdlmodule
        self.codes = []
        self.return_var = None

    def _emit(self, item, sched_time=0):
        assert item.is_a(AHDL_ASSIGN)
        self.codes.append(item)

    def _hooked_emit(self, ahdl, sched_time=0):
        self.hooked.append(ahdl)

    def _is_port_method(self, ir, method_name):
        if not ir.is_a(CALL):
            return False
        callee_scope = ir.get_callee_scope(self.scope)
        return (callee_scope.is_method() and
                callee_scope.parent.is_port() and
                callee_scope.base_name == method_name)

    def _is_net_method(self, ir, method_name):
        if not ir.is_a(CALL):
            return False
        callee_scope = ir.get_callee_scope(self.scope)
        return (callee_scope.is_method() and
                callee_scope.parent.name.startswith('polyphony.Net') and
                callee_scope.base_name == method_name)

    def visit_CALL(self, ir):
        if self._is_port_method(ir, 'rd'):
            port_var = cast(AHDL_VAR, self.visit(ir.func.exp))
            assert port_var.is_a(AHDL_VAR)
            return AHDL_VAR(port_var.vars, Ctx.LOAD)
        elif self._is_port_method(ir, 'edge'):
            old = ir.args[0][1]
            new = ir.args[1][1]
            port_var = cast(AHDL_VAR, self.visit(ir.func.exp))
            assert port_var.is_a(AHDL_VAR)
            port_var = AHDL_VAR(port_var.vars, Ctx.LOAD)
            _old = self.visit(old)
            _new = self.visit(new)
            self.hdlmodule.add_edge_detector(port_var, _old, _new)
            detect_var_name = f'is_{port_var.hdl_name}_change_{_old}_to_{_new}'
            detect_var_sig = self.hdlmodule.gen_sig(detect_var_name, 1, {'net'})
            return AHDL_VAR(detect_var_sig, Ctx.LOAD)
        elif self._is_net_method(ir, 'rd'):
            qsym = qualified_symbols(ir.func, self.scope)
            net_qsym = qsym[:-1]
            net_sig = self._net_sig(net_qsym)
            return AHDL_VAR(net_sig, Ctx.LOAD)
        else:
            assert False, 'NIY'

    def visit_SYSCALL(self, ir):
        assert False

    def visit_NEW(self, ir):
        assert False

    def visit_TEMP(self, ir):
        return super().visit_TEMP(ir)

    def visit_ATTR(self, ir):
        return super().visit_ATTR(ir)

    def visit_MREF(self, ir):
        return super().visit_MREF(ir)

    def visit_MSTORE(self, ir):
        assert False

    def visit_ARRAY(self, ir):
        assert False

    def visit_EXPR(self, ir):
        assert False

    def visit_CJUMP(self, ir):
        assert False

    def visit_MCJUMP(self, ir):
        assert False

    def visit_JUMP(self, ir):
        assert False

    def visit_RET(self, ir):
        self.return_var = self.visit(ir.exp)

    def visit_MOVE(self, ir):
        src = self.visit(ir.src)
        dst = self.visit(ir.dst)
        self._emit(AHDL_ASSIGN(dst, src))

    def visit_PHI(self, ir):
        assert ir.ps and len(ir.args) == len(ir.ps) and len(ir.args) > 1
        var_t = irexp_type(ir.var, self.scope)
        if var_t.is_seq():
            assert False, 'NIY'
        else:
            ahdl_dst, if_exp = self._make_scalar_mux(ir)
            self._emit(AHDL_ASSIGN(ahdl_dst, if_exp))

    def visit_CEXPR(self, ir):
        assert False

    def visit_CMOVE(self, ir):
        orig_emit_func = self._emit
        self._emit = self._hooked_emit
        self.hooked = []
        self.visit_MOVE(ir)
        self._emit = orig_emit_func
        for ahdl in self.hooked:
            cond = self.visit(ir.cond)
            rexp = AHDL_IF_EXP(cond, ahdl.src, AHDL_SYMBOL("'bz"))
            self._emit(AHDL_ASSIGN(ahdl.dst, rexp))
