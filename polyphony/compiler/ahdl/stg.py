import sys
from collections import OrderedDict, defaultdict
import functools
from .ahdl import *
from ..common.env import env
from ..ir.block import Block
from ..ir.ir import *
from ..ir.irvisitor import IRVisitor
from logging import getLogger
logger = getLogger(__name__)


class State(AHDL_BLOCK):
    def __init__(self, name, step, codes, stg):
        assert isinstance(name, str)
        super().__init__(name, codes)
        self.step = step
        self.stg = stg

    def __str__(self):
        s = '---------------------------------\n'
        s += f'{self.name}:{self.step}\n'
        if self.codes:
            for code in self.codes:
                str_code = str(code)
                lines = str_code.split('\n')
                for line in lines:
                    if line:
                        s += '  {}\n'.format(line)
        else:
            pass
        s += '\n'
        return s

    def __repr__(self):
        return self.name

    def traverse(self):
        for c in self.codes:
            yield c

    def resolve_transition(self, next_state, blk2states):
        code = self.codes[-1]
        if code.is_a(AHDL_TRANSITION):
            if code.target is None:
                code.target = next_state
            else:
                assert isinstance(code.target, Block)
                code.target = blk2states[code.target][0]
        elif code.is_a(AHDL_TRANSITION_IF):
            for i, ahdlblk in enumerate(code.blocks):
                assert len(ahdlblk.codes) == 1
                transition = ahdlblk.codes[0]
                assert transition.is_a(AHDL_TRANSITION)
                assert isinstance(transition.target, Block)
                target_state = blk2states[transition.target][0]
                transition.target = target_state
        return next_state


class STG(object):
    "State Transition Graph"
    def __init__(self, name, parent, states, hdlmodule):
        self.name = name
        logger.debug('#### stg ' + name)
        self.parent = parent
        if parent:
            logger.debug('#### parent stg ' + parent.name)
        self.states = []
        self.hdlmodule = hdlmodule
        self.scheduling = ''
        self.fsm = None

    def __str__(self):
        s = ''
        for state in self.states:
            s += str(state)
        return s

    def new_state(self, name, step, codes):
        return State(name, step, codes, self)

    def is_main(self):
        return not self.parent

    def get_top(self):
        if self.parent:
            return self.parent.get_top()
        else:
            return self

    def remove_state(self, state):
        state.states.remove(state)


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
        self.blk2states = {}

    def process(self, hdlmodule):
        self.hdlmodule = hdlmodule
        self.blk2states = {}
        if hdlmodule.scope.is_module():
            ctor = hdlmodule.scope.find_ctor()
            stgs = self._process_scope(ctor)
            fsm_name = stgs[0].name
            self.hdlmodule.add_fsm(fsm_name, ctor)
            self.hdlmodule.add_fsm_stg(fsm_name, stgs)

            for w, _ in hdlmodule.scope.workers:
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
        functools.reduce(lambda s1, s2: s1.resolve_transition(s2, self.blk2states), main_stg.states)
        if scope.is_worker() or scope.is_testbench():
            main_stg.states[-1].resolve_transition(main_stg.states[-1], self.blk2states)
        else:
            main_stg.states[-1].resolve_transition(main_stg.states[0], self.blk2states)
        for stg in stgs[1:]:
            functools.reduce(lambda s1, s2: s1.resolve_transition(s2, self.blk2states), stg.states)
            stg.states[-1].resolve_transition(stg.states[0], self.blk2states)

        return stgs

    def _get_parent_stg(self, dfg):
        return self.dfg2stg[dfg.parent]

    def _process_dfg(self, index, dfg):
        from .stg_pipeline import LoopPipelineStageBuilder, WorkerPipelineStageBuilder

        is_main = index == 0
        if self.scope.parent and self.scope.parent.is_module() and self.scope.is_callable():
            if is_main:
                stg_name = self.scope.parent.base_name
            else:
                stg_name = f'{self.scope.parent.base_name}_L{index}'
        else:
            if is_main:
                stg_name = self.scope.base_name
            else:
                stg_name = f'{self.scope.base_name}_L{index}'
            if self.scope.is_method():
                stg_name = self.scope.parent.base_name + '_' + stg_name

        parent_stg = self._get_parent_stg(dfg) if not is_main else None
        stg = STG(stg_name, parent_stg, None, self.hdlmodule)
        stg.scheduling = dfg.synth_params['scheduling']
        if stg.scheduling == 'pipeline':
            if not is_main:
                if self.scope.is_worker() and not dfg.region.counter:
                    builder = WorkerPipelineStageBuilder(self.scope, stg, self.blk2states)
                else:
                    builder = LoopPipelineStageBuilder(self.scope, stg, self.blk2states)
            elif is_main:
                builder = StateBuilder(self.scope, stg, self.blk2states)
        else:
            builder = StateBuilder(self.scope, stg, self.blk2states)
        builder.build(dfg, is_main)
        return stg


class STGItemBuilder(object):
    def __init__(self, scope, stg, blk2states):
        self.scope = scope
        self.hdlmodule = env.hdlmodule(scope)
        self.stg = stg
        self.blk2states = blk2states
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
        return self.stg.new_state(name, step, codes)

    #def emit(self, item, sched_time, node, tag=''):


class StateBuilder(STGItemBuilder):
    def __init__(self, scope, stg, blk2states):
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
            self.stg.states.extend(states)
            self.blk2states[blk] = states

    def _build_states_for_block(self, state_prefix, blk, is_main, is_first, is_last):
        states = []
        for step, items in self.scheduled_items.pop():
            codes = []
            for item, _ in items:
                if isinstance(item, AHDL):
                    codes.append(item)
                else:
                    assert False
            if not codes[-1].is_a([AHDL_TRANSITION, AHDL_TRANSITION_IF]):
                codes.append(AHDL_TRANSITION(None))
            name = f'{state_prefix}_S{step}'
            state = self._new_state(name, step + 1, codes)
            states.append(state)
        if not states:
            name = f'{state_prefix}_S0'
            codes = [AHDL_TRANSITION(None)]
            states = [self._new_state(name, 1, codes)]

        if blk.stms and blk.stms[-1].is_a(JUMP):
            jump = blk.stms[-1]
            last_state = states[-1]
            trans = last_state.codes[-1]
            assert trans.is_a([AHDL_TRANSITION])
            if trans.is_a(AHDL_TRANSITION):
                trans.target = jump.target

        # deal with the first/last state
        if not is_main:
            pass
        elif self.scope.is_worker() or self.scope.is_testbench():
            if is_first:
                name = f'{state_prefix}_INIT'
                init_state = states[0]
                init_state.name = name
                assert init_state.codes[-1].is_a([AHDL_TRANSITION,
                                                  AHDL_TRANSITION_IF])
            if is_last:
                last_state = states[-1]
                if self.scope.is_loop_worker():
                    codes = [AHDL_TRANSITION(self.scope.entry_block)]
                elif self.scope.is_worker():
                    codes = [AHDL_TRANSITION(None)]
                elif self.scope.is_testbench():
                    codes = [
                        AHDL_INLINE('$display("%5t:finish", $time);'),
                        AHDL_INLINE('$finish();')
                    ]
                finish_state = self._new_state(f'{state_prefix}_FINISH',
                                               last_state.step + 1,
                                               codes)
                states.append(finish_state)
        else:
            if is_first:
                first_state = states[0]
                assert first_state.codes[-1].is_a([AHDL_TRANSITION, AHDL_TRANSITION_IF])
                prolog = AHDL_SEQ(AHDL_CALLEE_PROLOG(self.stg.name), 0, 1)
                first_state.codes.insert(0, prolog)
                first_state.name = f'{state_prefix}_INIT'
            if is_last:
                name = f'{state_prefix}_FINISH'
                finish_state = states[-1]
                finish_state.name = name
                assert finish_state.codes[-1].is_a(AHDL_TRANSITION)
                epilog = AHDL_SEQ(AHDL_CALLEE_EPILOG(self.stg.name), 0, 1)
                finish_state.codes.insert(-1, epilog)
        return states


def _signal_width(sym):
    width = -1
    if sym.typ.is_seq():
        width = (sym.typ.get_element().get_width(), sym.typ.get_length())
    elif sym.typ.is_int() or sym.typ.is_bool():
        width = sym.typ.get_width()
    elif sym.typ.is_port():
        width = sym.typ.get_dtype().get_width()
    elif sym.typ.is_object():
        width = 16
    elif sym.is_condition():
        width = 1
    return width


def _tags_from_sym(sym):
    tags = set()
    if sym.typ.is_int():
        if sym.typ.get_signed():
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
        elm_t = sym.typ.get_element()
        if elm_t.is_int() and elm_t.get_signed():
            tags.add('int')
        if sym.scope.is_containable():
            tags.add('rom')
        elif sym.is_alias():
            tags.add('netarray')
        else:
            tags.add('regarray')
    elif sym.typ.is_list():
        elm_t = sym.typ.get_element()
        if elm_t.is_int() and elm_t.get_signed():
            tags.add('int')
        if sym.typ.get_ro() and sym.scope.is_containable():
            tags.add('rom')
        else:
            tags.add('regarray')
    elif sym.typ.is_port():
        di = sym.typ.get_direction()
        assert di != '?'
        if di != 'inout':
            tags.add(di)
    elif sym.typ.is_object():
        if sym.typ.get_scope().orig_name == 'polyphony.Reg':
            assert not sym.is_alias()
            tags.add('reg')
        elif sym.typ.get_scope().orig_name == 'polyphony.Net':
            assert sym.is_alias()
            tags.add('net')

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
        self.hdlmodule = env.hdlmodule(scope)
        self.scheduled_items = None

    def process_node(self, node):
        self.node = node
        self.visit(node.tag)

    def set_sched_time(self, sched_time):
        self.sched_time = sched_time

    def get_signal_prefix(self, ir):
        assert ir.is_a(CALL)
        if ir.func_scope().is_class():
            assert self.current_stm.is_a(MOVE)
            name = self.current_stm.dst.symbol().name
            return f'{name}_{env.ctor_name}'
        elif ir.func_scope().is_method():
            assert ir.func.is_a(ATTR)
            instance_name = self.make_instance_name(ir.func)
            return f'{instance_name}_{ir.func.attr.name}'
        else:
            assert ir.func.is_a(TEMP)
            name = ir.func_scope().base_name
            n = self.node.instance_num
            return f'{name}_{n}'

    def make_instance_name(self, ir):
        assert ir.is_a(ATTR)

        def make_instance_name_rec(ir):
            assert ir.is_a(ATTR)
            if ir.exp.is_a(TEMP):
                if ir.exp.sym.name == env.self_name:
                    if self.scope.is_ctor():
                        return self.scope.parent.base_name
                    else:
                        return self.scope.base_name
                elif ir.exp.sym.typ.is_class():
                    return ir.exp.sym.typ.get_scope().base_name
                else:
                    return ir.exp.sym.hdl_name()
            else:
                exp_name = make_instance_name_rec(ir.exp)
                attr_name = ir.exp.attr.name
                instance_name = f'{exp_name}_{attr_name}'
            return instance_name
        return make_instance_name_rec(ir)

    def _emit(self, item, sched_time):
        logger.debug('emit ' + str(item) + ' at ' + str(sched_time))
        self.scheduled_items.push(sched_time, item, tag='')
        self.hdlmodule.ahdl2dfgnode[item] = self.node

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
        if ir.func_scope().is_method():
            instance_name = self.make_instance_name(ir.func)
        else:
            qname = ir.func_scope().qualified_name()
            n = self.node.instance_num
            instance_name = f'{qname}_{n}'
        signal_prefix = self.get_signal_prefix(ir)
        callargs = self._visit_args(ir)
        if not ir.func_scope().is_method():
            self.scope.append_callee_instance(ir.func_scope(), instance_name)

        ahdl_call = AHDL_MODULECALL(ir.func_scope(), callargs, instance_name, signal_prefix)
        return ahdl_call

    def visit_NEW(self, ir):
        assert self.current_stm.is_a(MOVE)
        mv = self.current_stm
        instance_name = mv.dst.symbol().hdl_name()
        signal_prefix = '{}_{}'.format(instance_name, env.ctor_name)
        callargs = self._visit_args(ir)
        self.scope.append_callee_instance(ir.func_scope(), instance_name)

        ahdl_call = AHDL_MODULECALL(ir.func_scope(), callargs, instance_name, signal_prefix)
        return ahdl_call

    def translate_builtin_len(self, syscall):
        _, mem = syscall.args[0]
        assert mem.is_a(TEMP)
        assert mem.symbol().typ.is_seq()
        assert isinstance(mem.symbol().typ.get_length(), int)
        return AHDL_CONST(mem.symbol().typ.get_length())

    def visit_SYSCALL(self, ir):
        logger.debug(ir.sym.name)
        if ir.sym.name == 'print':
            fname = '!hdl_print'
        elif ir.sym.name == 'assert':
            fname = '!hdl_assert'
        elif ir.sym.name == 'polyphony.verilog.display':
            fname = '!hdl_verilog_display'
        elif ir.sym.name == 'polyphony.verilog.write':
            fname = '!hdl_verilog_write'
        elif ir.sym.name == 'len':
            return self.translate_builtin_len(ir)
        elif ir.sym.name == '$new':
            _, arg = ir.args[0]
            self.visit(arg)
            return AHDL_CONST(self.current_stm.dst.symbol().id)
        elif ir.sym.name == 'polyphony.timing.clksleep':
            _, cycle = ir.args[0]
            assert cycle.is_a(CONST)
            for i in range(cycle.value):
                self._emit(AHDL_NOP('wait a cycle'),
                           self.sched_time + i)
            return
        elif ir.sym.name == 'polyphony.timing.clktime':
            self.hdlmodule.use_clock_time()
            return AHDL_VAR(self.hdlmodule.clock_signal, Ctx.LOAD)
        elif ir.sym.name in ('polyphony.timing.wait_rising',
                             'polyphony.timing.wait_falling',
                             'polyphony.timing.wait_edge',
                             'polyphony.timing.wait_value'):
            assert False, 'It must be inlined'
        elif ir.sym.name == 'polyphony.timing.wait_until':
            scope_sym = ir.args[0][1].symbol()
            assert scope_sym.typ.is_function()
            pred = scope_sym.typ.get_scope()
            #assert pred.is_assigned()
            translator = AHDLCombTranslator(self.hdlmodule, self.scope)
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
        args = []
        for i, (_, arg) in enumerate(ir.args):
            a = self.visit(arg)
            args.append(a)
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
        typ = ir.mem.symbol().typ
        # Only static class or global field can be hdl function
        if ir.mem.symbol().scope.is_containable() and (typ.is_tuple() or typ.is_list() and typ.get_ro()):
            return AHDL_FUNCALL(memvar, [offset])
        else:
            return AHDL_SUBSCRIPT(memvar, offset)

    def visit_MSTORE(self, ir):
        offset = self.visit(ir.offset)
        exp = self.visit(ir.exp)
        memvar = self.visit(ir.mem)
        memvar.ctx = Ctx.STORE
        dst = AHDL_SUBSCRIPT(memvar, offset)
        self._emit(AHDL_MOVE(dst, exp), self.sched_time)
        return None

    def _build_mem_initialize_seq(self, array, memvar):
        name = memvar.sig.name  # sym.hdl_name()
        sym = self.current_stm.dst.symbol()
        width = sym.typ.get_element().get_width()
        length = sym.typ.get_length()
        if memvar.sig.is_netarray():
            sig = self.hdlmodule.gen_sig(name, (width, length), {'netarray'}, sym)
        else:
            sig = self.hdlmodule.gen_sig(name, (width, length), {'regarray'}, sym)
        for i, item in enumerate(array.items):
            if not(isinstance(item, CONST) and item.value is None):
                idx = AHDL_CONST(i)
                memvar = AHDL_MEMVAR(sig, Ctx.STORE)
                ahdl_item = self.visit(item)
                ahdl_move = AHDL_MOVE(AHDL_SUBSCRIPT(memvar, idx), ahdl_item)
                self._emit(ahdl_move, self.sched_time)

    def visit_ARRAY(self, ir):
        # array expansion
        assert ir.repeat.is_a(CONST)
        ir.items = [item.clone() for item in ir.items * ir.repeat.value]

        assert isinstance(self.current_stm, MOVE)
        sym = self.current_stm.dst.symbol()
        if sym.scope.is_containable() and (sym.typ.is_tuple() or sym.typ.is_list() and sym.typ.get_ro()):
            # this array will be rom
            pass
        else:
            ahdl_memvar = self.visit(self.current_stm.dst)
            self._build_mem_initialize_seq(ir, ahdl_memvar)

    def visit_TEMP(self, ir):
        sym = ir.symbol()
        sig = self._make_signal((sym,))
        if sym.typ.is_seq():
            return AHDL_MEMVAR(sig, ir.ctx)
        else:
            return AHDL_VAR(sig, ir.ctx)

    def visit_ATTR(self, ir):
        sym = ir.symbol()
        qsym = ir.qualified_symbol()
        sig = self._make_signal(qsym)
        if sym.typ.is_seq():
            return AHDL_MEMVAR(sig, ir.ctx)
        else:
            return AHDL_VAR(sig, ir.ctx)

    def _make_signal(self, qsym):
        sig = self.hdlmodule.signal(qsym[-1])
        if sig:
            return sig
        tags = _tags_from_sym(qsym[-1])
        width = _signal_width(qsym[-1])

        if len(qsym) >= 2:
            if qsym[-1].scope.is_unflatten():
                qsym = qsym[:-1]
            if qsym[0].typ.is_object():
                if qsym[0].typ.get_scope().is_module():
                    assert qsym[0].name.startswith(env.self_name)
                    tags.add('field')
                    qsym = qsym[1:]  # skip 'self'
                sig_name = '_'.join([sym.hdl_name() for sym in qsym])
            elif qsym[0].typ.is_class():
                sig_name = '_'.join([sym.hdl_name() for sym in qsym])
            else:
                assert False
        else:
            if qsym[-1].scope is not self.scope:
                sig_name = qsym[-1].hdl_name()
            elif self.scope.is_worker() or self.scope.is_method():
                is_param = False
                if self.scope.is_ctor() and self.scope.parent.is_module() and self.scope.parent.module_params:
                    is_param = any((qsym[-1] is copy for _, copy, _ in self.scope.parent.module_params))
                if is_param:
                    sig_name = qsym[-1].hdl_name()
                    tags.update({'parameter'})
                    if 'reg' in tags:
                        tags.remove('reg')
                else:
                    sig_name = f'{self.scope.base_name}_{qsym[-1].hdl_name()}'
            elif qsym[-1].is_param():
                sig_name = f'{self.scope.base_name}_{qsym[-1].hdl_name()}'
            elif qsym[-1].is_return():
                sig_name = f'{self.scope.base_name}_out_0'
            else:
                sig_name = qsym[-1].hdl_name()
        sig = self.hdlmodule.gen_sig(sig_name, width, tags, qsym[-1])
        return sig

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
            self._emit(AHDL_TRANSITION(ir.true), self.sched_time)
        else:
            cond_list = [cond, AHDL_CONST(1)]
            blocks = [AHDL_BLOCK('', [AHDL_TRANSITION(ir.true)]),
                      AHDL_BLOCK('', [AHDL_TRANSITION(ir.false)])]
            self._emit(AHDL_TRANSITION_IF(cond_list, blocks), self.sched_time)

    def visit_JUMP(self, ir):
        self._emit(AHDL_TRANSITION(ir.target), self.sched_time)

    def visit_MCJUMP(self, ir):
        for c, target in zip(ir.conds[:-1], ir.targets[:-1]):
            if c.is_a(CONST) and c.value == 1:
                cond = self.visit(c)
                self._emit(AHDL_TRANSITION(target), self.sched_time)
                return

        cond_list = []
        blocks = []
        for c, target in zip(ir.conds, ir.targets):
            cond = self.visit(c)
            cond_list.append(cond)
            blocks.append(AHDL_BLOCK('', [AHDL_TRANSITION(target)]))
        self._emit(AHDL_TRANSITION_IF(cond_list, blocks), self.sched_time)

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
        if ir.is_a(MOVE) and ir.src.is_a([NEW, CALL]) and ir.src.func_scope().is_module():
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
        elif ir.src.is_a(TEMP) and ir.src.sym.is_param():
            if ir.src.sym.name.endswith(env.self_name):
                return
            elif ir.src.sym.typ.is_object() and ir.src.sym.typ.get_scope().is_module():
                return
            elif ir.src.sym.typ.is_port():
                return
        elif ir.src.is_a([TEMP, ATTR]) and ir.src.symbol().typ.is_port():
            return
        src = self.visit(ir.src)
        dst = self.visit(ir.dst)
        if not src:
            return
        elif src.is_a(AHDL_VAR) and dst.is_a(AHDL_VAR) and src.sig == dst.sig:
            return
        elif dst.is_a(AHDL_MEMVAR) and src.is_a(AHDL_MEMVAR):
            if ir.src.sym.is_param():
                width = ir.src.sym.typ.get_element().get_width()
                length = ir.src.sym.typ.get_length()
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
            dst.sig.init_value = src.value
        self._emit(AHDL_MOVE(dst, src), self.sched_time)

    def visit_PHI(self, ir):
        assert ir.ps and len(ir.args) == len(ir.ps) and len(ir.args) > 1
        ahdl_dst, if_exp = self._make_scalar_mux(ir)
        self._emit(AHDL_MOVE(ahdl_dst, if_exp), self.sched_time)

    def _emit_call_sequence(self, ahdl_call, dst, sched_time):
        assert ahdl_call.is_a(AHDL_MODULECALL)
        for arg in ahdl_call.args:
            if arg.is_a(AHDL_MEMVAR):
                ahdl_call.returns.append(arg)
        # TODO:
        if dst:
            ahdl_call.returns.append(dst)

        step_n = self.node.latency()
        for i in range(step_n):
            self._emit(AHDL_SEQ(ahdl_call, i, step_n), sched_time + i)

    def _make_scalar_mux(self, ir):
        ahdl_dst = self.visit(ir.var)
        arg_p = list(zip(ir.args, ir.ps))
        rexp, cond = arg_p[-1]
        cond = self.visit(cond)
        if cond.is_a(CONST) and cond.value:
            rexp = self.visit(rexp)
        else:
            lexp = self.visit(rexp)
            rexp = AHDL_IF_EXP(cond, lexp, AHDL_SYMBOL("'bz"))
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
            ahdl.guard_cond = cond
            if ahdl.is_a(AHDL_SEQ) and ahdl.step == 0:
                ahdl.factor.guard_cond = cond
            self._emit(AHDL_IF([cond], [AHDL_BLOCK('', [ahdl])]), sched_time)

    def visit_CMOVE(self, ir):
        orig_emit_func = self._emit
        self._emit = self._hooked_emit
        self.hooked = []
        self.visit_MOVE(ir)
        self._emit = orig_emit_func
        for ahdl, sched_time in self.hooked:
            cond = self.visit(ir.cond)
            ahdl.guard_cond = cond
            if ahdl.is_a(AHDL_SEQ) and ahdl.step == 0:
                ahdl.factor.guard_cond = cond
            self._emit(AHDL_IF([cond], [AHDL_BLOCK('', [ahdl])]), sched_time)

    def _is_port_method(self, ir):
        return ir.is_a(CALL) and ir.func_scope().is_method() and ir.func_scope().parent.is_port()

    def _is_net_method(self, ir):
        return ir.is_a(CALL) and ir.func_scope().is_method() and ir.func_scope().parent.name.startswith('polyphony.Net')

    def _is_port_ctor(self, ir):
        return ir.is_a(NEW) and ir.func_scope().is_port()

    def _is_net_ctor(self, ir):
        return ir.is_a(NEW) and ir.func_scope().name.startswith('polyphony.Net')

    def _port_sig(self, port_qsym):
        assert port_qsym[-1].typ.is_port()
        port_sym = port_qsym[-1]
        root_sym = port_sym.typ.get_root_symbol()
        port_prefixes = port_qsym[:-1] + (root_sym,)

        if port_prefixes[0].name == env.self_name:
            port_prefixes = port_prefixes[1:]
        port_name = '_'.join([pfx.hdl_name() for pfx in port_prefixes])
        port_sig = env.hdlmodule(port_sym.scope).signal(port_name)
        if port_sig:
            tags = port_sig.tags
        else:
            tags = set()
        dtype = port_sym.typ.get_dtype()
        width = dtype.get_width()
        port_scope = port_sym.typ.get_scope()
        # kind and direction might be changed at root
        # so we use root_sym.typ
        kind = root_sym.typ.get_port_kind()
        direction = root_sym.typ.get_direction()
        assert direction != '?'
        assigned = root_sym.typ.get_assigned()
        assert port_scope.base_name.startswith('Port')
        tags.add('single_port')
        if dtype.has_signed() and dtype.get_signed():
            tags.add('int')

        outer_module_scope = self.scope.outer_module()
        if kind == 'internal':
            if assigned:
                tags.add('net')
            else:
                tags.add('reg')
        elif outer_module_scope:
            if direction == 'input':
                tags.add('input')
                tags.add('net')
            elif direction == 'output':
                tags.add('output')
                tags.add('reg')
        else:
            # TODO
            tags.add('extport')
            if direction == 'input':
                tags.add('reg')
            elif direction == 'output':
                tags.add('net')
            else:
                assert False
        is_pipeline_access = self.current_stm.block.synth_params['scheduling'] == 'pipeline'
        if root_sym.is_pipelined() and is_pipeline_access:
            tags.add('pipelined')

        if 'extport' in tags:
            port_sig = self.hdlmodule.gen_sig(port_name, width, tags, port_sym)
        else:
            assert outer_module_scope
            port_sig = env.hdlmodule(outer_module_scope).gen_sig(port_name, width, tags, port_sym)
        if port_sym.typ.has_init() and not assigned:
            tags.add('initializable')
            if dtype.is_int():
                port_sig.init_value = port_sym.typ.get_init()
            elif dtype.is_bool():
                port_sig.init_value = 1 if port_sym.typ.get_init() else 0
            else:
                assert False
        if port_sym.typ.has_maxsize():
            port_sig.maxsize = port_sym.typ.get_maxsize()
        # TODO: get_rewritable to be always available
        if port_sym.typ.get_rewritable():
            tags.add('rewritable')
        return port_sig

    def _make_port_access(self, call, target):
        assert call.func.is_a(ATTR)
        port_qsym = call.func.qualified_symbol()[:-1]
        port_sig = self._port_sig(port_qsym)

        if call.func_scope().base_name == 'wr':
            self._make_port_write_seq(call, port_sig)
        elif call.func_scope().base_name == 'rd':
            self._make_port_read_seq(target, port_sig)
        elif call.func_scope().base_name == 'assign':
            self._make_port_assign(call.args[0][1].symbol(), port_sig)
        elif call.func_scope().base_name == 'edge':
            self._make_port_edge(target, port_sig, call.args[0][1], call.args[1][1])
        else:
            assert False

    def _make_port_write_seq(self, call, port_sig):
        assert call.args
        _, val = call.args[0]
        src = self.visit(val)
        iow = AHDL_IO_WRITE(AHDL_VAR(port_sig, Ctx.STORE),
                            src,
                            port_sig.is_output())
        assert port_sig.is_single_port()
        self._emit(iow, self.sched_time)

    def _make_port_read_seq(self, target, port_sig):
        if target:
            dst = self.visit(target)
        else:
            dst = None
        ior = AHDL_IO_READ(AHDL_VAR(port_sig, Ctx.LOAD),
                           dst,
                           port_sig.is_input())
        assert port_sig.is_single_port()
        self._emit(ior, self.sched_time)

    def _make_port_assign(self, scope_sym, port_sig):
        assert scope_sym.typ.is_function()
        assigned = scope_sym.typ.get_scope()
        assert assigned.is_assigned()
        translator = AHDLCombTranslator(self.hdlmodule, self.scope)
        translator.process(assigned)
        for assign in translator.codes:
            self.hdlmodule.add_static_assignment(assign)
        assign = AHDL_ASSIGN(AHDL_VAR(port_sig, Ctx.STORE),
                             translator.return_var)
        self.hdlmodule.add_static_assignment(assign)
        port_sig.del_tag('reg')
        port_sig.del_tag('initializable')
        port_sig.add_tag('net')

    def _make_port_edge(self, target, port_sig, old, new):
        if target:
            dst = self.visit(target)
        else:
            dst = None
        assert 'net' in dst.sig.tags
        _old = self.visit(old)
        _new = self.visit(new)
        self.hdlmodule.add_edge_detector(port_sig, _old, _new)
        detect_var_name = f'is_{port_sig.name}_change_{_old}_to_{_new}'
        detect_var_sig = self.hdlmodule.gen_sig(detect_var_name, 1, {'net'})
        edge = AHDL_VAR(detect_var_sig, Ctx.LOAD)
        self._emit(AHDL_MOVE(dst, edge), self.sched_time)

    def _make_port_init(self, new, target):
        assert new.func_scope().is_port()
        port = target.symbol().typ
        assert port.is_port()
        # make port signal
        self._port_sig(target.qualified_symbol())

    def _is_module_method(self, ir):
        return ir.is_a(CALL) and ir.func_scope().is_method() and ir.func_scope().parent.is_module()

    def _net_sig(self, net_qsym):
        net_sym = net_qsym[-1]
        net_prefixes = net_qsym

        if net_prefixes[0].name == env.self_name:
            net_prefixes = net_prefixes[1:]
        net_name = '_'.join([pfx.hdl_name() for pfx in net_prefixes])

        dtype = net_sym.typ.get_scope().type_args[0]
        width = dtype.get_width()
        tags = {'net'}
        net_sig = env.hdlmodule(net_sym.scope).signal(net_name)
        if net_sig:
            net_sig.tags.update(tags)
            return net_sig
        net_sig = self.hdlmodule.gen_sig(net_name, width, tags, net_sym)
        return net_sig

    def _make_net_init(self, new, target):
        net_sig = self._net_sig(target.qualified_symbol())
        scope_sym = new.args[0][1].symbol()
        assert scope_sym.typ.is_function()
        assigned = scope_sym.typ.get_scope()
        assert assigned.is_assigned()
        translator = AHDLCombTranslator(self.hdlmodule, self.scope)
        translator.process(assigned)
        for assign in translator.codes:
            self.hdlmodule.add_static_assignment(assign)
        assign = AHDL_ASSIGN(AHDL_VAR(net_sig, Ctx.STORE),
                             translator.return_var)
        self.hdlmodule.add_static_assignment(assign)

    def _make_net_access(self, call, target):
        assert call.func.is_a(ATTR)
        net_qsym = call.func.qualified_symbol()[:-1]
        net_sig = self._net_sig(net_qsym)

        if call.func_scope().base_name == 'rd':
            self._make_net_read_seq(target, net_sig)
        elif call.func_scope().base_name == 'assign':
            self._make_net_assign(call.args[0][1].symbol(), net_sig)
        else:
            assert False

    def _make_net_read_seq(self, target, net_sig):
        if target:
            dst = self.visit(target)
            mv = AHDL_MOVE(dst, AHDL_VAR(net_sig, Ctx.LOAD))
            self._emit(mv, self.sched_time)

    def _make_net_assign(self, scope_sym, net_sig):
        assert scope_sym.typ.is_function()
        assigned = scope_sym.typ.get_scope()
        assert assigned.is_assigned()
        translator = AHDLCombTranslator(self.hdlmodule, self.scope)
        translator.process(assigned)
        for assign in translator.codes:
            self.hdlmodule.add_static_assignment(assign)
        assign = AHDL_ASSIGN(AHDL_VAR(net_sig, Ctx.STORE),
                             translator.return_var)
        self.hdlmodule.add_static_assignment(assign)
        assert net_sig.is_net()


class AHDLCombTranslator(AHDLTranslator):
    def __init__(self, hdlmodule, scope):
        self.hdlmodule = hdlmodule
        self.scope = scope
        self.codes = []
        self.return_var = None

    def _emit(self, item, sched_time=0):
        assert item.is_a(AHDL_ASSIGN)
        self.codes.append(item)

    def _hooked_emit(self, ahdl, sched_time=0):
        self.hooked.append(ahdl)

    def _is_port_method(self, ir, method_name):
        return (ir.is_a(CALL) and
                ir.func_scope().is_method() and
                ir.func_scope().parent.is_port() and
                ir.func_scope().base_name == method_name)

    def _is_net_method(self, ir, method_name):
        return (ir.is_a(CALL) and
                ir.func_scope().is_method() and
                ir.func_scope().parent.name.startswith('polyphony.Net') and
                ir.func_scope().base_name == method_name)

    def visit_CALL(self, ir):
        if self._is_port_method(ir, 'rd'):
            port_qsym = ir.func.qualified_symbol()[:-1]
            port_sig = self._port_sig(port_qsym)
            return AHDL_VAR(port_sig, Ctx.LOAD)
        elif self._is_port_method(ir, 'edge'):
            old = ir.args[0][1]
            new = ir.args[1][1]
            port_qsym = ir.func.qualified_symbol()[:-1]
            port_sig = self._port_sig(port_qsym)
            _old = self.visit(old)
            _new = self.visit(new)
            self.hdlmodule.add_edge_detector(port_sig, _old, _new)
            detect_var_name = f'is_{port_sig.name}_change_{_old}_to_{_new}'
            detect_var_sig = self.hdlmodule.gen_sig(detect_var_name, 1, {'net'})
            return AHDL_VAR(detect_var_sig, Ctx.LOAD)
        elif self._is_net_method(ir, 'rd'):
            net_qsym = ir.func.qualified_symbol()[:-1]
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
        if ir.var.symbol().typ.is_seq():
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
            ahdl.guard_cond = cond
            rexp = AHDL_IF_EXP(cond, ahdl.src, AHDL_SYMBOL("'bz"))
            self._emit(AHDL_ASSIGN(ahdl.dst, rexp))
