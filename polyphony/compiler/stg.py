import sys
from collections import OrderedDict, defaultdict, deque
import functools
from .block import Block
from .ir import *
from .ahdl import *
from .latency import get_latency
from .common import INT_WIDTH, error_info
from .type import Type
from .symbol import Symbol
from .env import env
from .memref import *
from logging import getLogger
logger = getLogger(__name__)
import pdb


class State:
    def __init__(self, name, step, codes, stg):
        assert isinstance(name, str)
        self.name = name
        self.step = step
        self.codes = codes
        self.next_states = []
        self.prev_states = []
        self.stg = stg

    def __str__(self):
        def _strcodes(codes):
            if codes: return ', '.join([str(c) for c in codes])
            else:     return ''
        s = '---------------------------------\n'
        s += '{}:{}'.format(self.name, self.step)
        if self.codes or self.next_states:
            s += '\n'
            if self.codes:
                s += '\n'.join(['  {}'.format(code) for code in self.codes])
            s += '\n'
        else:
            pass
        s += '\n'
        return s

    def __repr__(self):
        return self.name

    def append_next(self, next_state):
        self.next_states.append(next_state)
        next_state.append_prev(self)
        logger.debug('set_next ' + self.name + ' next:' + next_state.name)
        if next_state.step == sys.maxsize:
            next_state.step = self.step + 1

    def append_prev(self, prev):
        self.prev_states.append(prev)

    def replace_next(self, old_state, new_state):
        for i, nstate in enumerate(self.next_states):
            if nstate is old_state:
                self.next_states[i] = new_state

    def clear_next(self):
        for nstate in self.next_states:
            nstate.prev_states.remove(self)
        self.next_states = []

    def resolve_transition(self, next_state):
        code = self.codes[-1]
        if code.is_a(AHDL_TRANSITION):
            if code.target is None:
                code.target = next_state
            else:
                assert isinstance(code.target, Block)
                code.target = self.stg.scope.blk2state[code.target][0]
            self.append_next(code.target)
            transition = code
        elif code.is_a(AHDL_TRANSITION_IF):
            for codes in code.codes_list:
                c = codes[-1]
                assert c.is_a(AHDL_TRANSITION)
                assert isinstance(c.target, Block)
                c.target = self.stg.scope.blk2state[c.target][0]
                self.append_next(c.target)
            transition = code
        else:
            self.append_next(next_state)
            transition = None

        move_transition = False
        for code in self.codes:
           if code.is_a(AHDL_META_WAIT):
               if transition:
                   code.transition = transition
                   move_transition = True
               else:
                   code.transition = AHDL_TRANSITION(next_state)
        if move_transition:
            self.codes.pop()
        return next_state

    def merge_wait_ret(self):
        first_wait_ret = None
        removes = []
        for code in self.codes:
            if not (code.is_a(AHDL_META_WAIT) and code.metaid == 'WAIT_RET_AND_GATE'):
                continue

            if first_wait_ret is None:
                first_wait_ret = code
            else:
                modulecall = code.args[0][0]
                first_wait_ret.args[0].append(modulecall)
                removes.append(code)
        for code in removes:
            self.codes.remove(code)

    def merge_wait_input_ready(self):
        wait_input_ready = None
        removes = []
        for code in self.codes:
            if code.is_a(AHDL_META_WAIT) and code.metaid == 'WAIT_INPUT_READY':
                wait_input_ready = code
            else:
                removes.append(code)
        if wait_input_ready:
            wait_input_ready.codes = removes[:]
            for code in removes:
                self.codes.remove(code)
        
class STG:
    "State Transition Graph"
    def __init__(self, name, parent, states, scope):
        self.name = name
        logger.debug('#### stg ' + name)
        self.parent = parent
        if parent:
            logger.debug('#### parent stg ' + parent.name)
        self.states = []
        self.scope = scope
        self.init_state = None
        self.finish_state = None

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

    
class ScheduledItemQueue:
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


class STGBuilder:
    def __init__(self):
        self.dfg2stg = {}
        self.mrg = env.memref_graph

    def process(self, scope):
        if scope.is_class():
            return
        self.scope = scope
        self.scope.blk2state = {}

        stgs = []
        dfgs = scope.dfgs(bottom_up=False)
        for i, dfg in enumerate(dfgs):
            stg = self._process_dfg(i, dfg)
            stgs.append(stg)
            self.dfg2stg[dfg] = stg

        for stg in stgs:
            functools.reduce(lambda s1, s2: s1.resolve_transition(s2), stg.states)
            stg.states[-1].resolve_transition(stg.states[0])

        stgs[0].states[0].merge_wait_input_ready()
        for stg in stgs:
            for state in stg.states:
                state.merge_wait_ret()

        scope.stgs = stgs

    def _get_parent_stg(self, dfg):
        return self.dfg2stg[dfg.parent]

    def _get_block_nodes_map(self, dfg):
        blk_nodes_map = defaultdict(list)
        for n in dfg.get_scheduled_nodes():
            if n.begin < 0:
                continue
            blk = n.tag.block
            blk_nodes_map[blk].append(n)
        return blk_nodes_map

    def _process_dfg(self, index, dfg):
        is_main = index == 0
        stg_name = self.scope.orig_name if is_main else 'L{}'.format(index)
        if self.scope.is_method():
            stg_name = self.scope.parent.orig_name + '_' + stg_name
        self.translator = AHDLTranslator(stg_name, self, self.scope)

        parent_stg = self._get_parent_stg(dfg) if not is_main else None
        self.stg = STG(stg_name, parent_stg, None, self.scope)

        blk_nodes_map = self._get_block_nodes_map(dfg)
        for i, blk in enumerate(dfg.blocks):
            blk_name = blk.nametag + str(blk.num)
            state_prefix = stg_name + '_' + blk_name
            logger.debug('# BLOCK ' + state_prefix + ' #')
            is_first = True if i == 0 else False
            is_last = True if i == len(dfg.blocks)-1 else False

            self.scheduled_items = ScheduledItemQueue()
            if blk in blk_nodes_map:
                nodes = blk_nodes_map[blk]
                self._build_scheduled_items(nodes)
            states = self._build_states(state_prefix, blk, is_main, is_first, is_last)
            assert states

            self.stg.states.extend(states)
            self.scope.blk2state[blk] = states

        return self.stg


    def _build_scheduled_items(self, nodes):
        scheduled_node_map = OrderedDict()
        max_sched_time = 0
        for n in nodes:
            if n.begin not in scheduled_node_map:
                scheduled_node_map[n.begin] = []
            scheduled_node_map[n.begin].append(n)
            max_sched_time = n.begin

        last_step = 0
        scheduled_node_list = []
        for step, nodes in scheduled_node_map.items():
            delta = step - last_step
            last_step = step
            scheduled_node_list.append((delta, nodes))
        self.cur_sched_time = 0
        for delta, nodes in scheduled_node_list:
            self.cur_sched_time += delta
            self._translate_nodes(nodes)


    def _translate_nodes(self, nodes):
        ''' translates IR to AHDL or Transition, and emit to scheduled_items'''
        self.translator.reset(self.cur_sched_time)
        for node in nodes:
            self.translator.visit(node.tag, node)

    def _build_states(self, state_prefix, blk, is_main, is_first, is_last):
        states = []
        for step, items in self.scheduled_items.pop():
            codes = []
            for item, _ in items:
                if isinstance(item, AHDL):
                    codes.append(item)
                else:
                    assert False
            if not codes[-1].is_a([AHDL_TRANSITION, AHDL_TRANSITION_IF, AHDL_META_WAIT]):
                codes.append(AHDL_TRANSITION(None))
            name = '{}_S{}'.format(state_prefix, step)
            state = self._new_state(name, step+1, codes)
            states.append(state)
        if not states:
            name = '{}_S{}'.format(state_prefix, 0)
            codes = [AHDL_TRANSITION(None)]
            states = [self._new_state(name, 1, codes)]

        if blk.stms[-1].is_a(JUMP):
            jump = blk.stms[-1]
            last_state = states[-1]
            trans = last_state.codes[-1]
            assert trans.is_a(AHDL_TRANSITION)
            trans.target = jump.target

        # deal with the first/last state
        if is_main:
            if is_first:
                name = '{}_INIT'.format(state_prefix)
                init_state = states[0]
                init_state.name = name
                assert init_state.codes[-1].is_a([AHDL_TRANSITION, AHDL_TRANSITION_IF])
                if not (len(states) <= 1 and is_last):
                    pos = len(init_state.codes)-1
                    init_state.codes.insert(pos, AHDL_META_WAIT("WAIT_INPUT_READY", self.stg.name))
                self.stg.init_state = init_state
            if is_last:
                name = '{}_FINISH'.format(state_prefix)
                finish_state = states[-1]
                finish_state.name = name
                assert finish_state.codes[-1].is_a(AHDL_TRANSITION)
                finish_state.codes[-1] = AHDL_META_WAIT("WAIT_OUTPUT_ACCEPT", self.stg.name)
                self.stg.finish_state = finish_state
        return states

    def gen_sig(self, prefix, postfix, width, attr = None):
        sig = self.scope.gen_sig('{}_{}'.format(prefix, postfix), width, attr)
        return sig

    def _new_state(self, name, step, codes):
        return self.stg.new_state(name, step, codes)

    def emit_call_ret_sequence(self, ahdl_call, dst, latency, sched_time):
        self.emit(AHDL_META('SET_READY', ahdl_call, 0), sched_time + 1)

        sched_time = sched_time + latency - 1
        # We must emit 'WAIT_RET_AND_GATE' before '*_IF_VALID' for test-bench sequence
        self.emit(AHDL_META_WAIT('WAIT_RET_AND_GATE', [ahdl_call]), sched_time)
        self.emit(AHDL_META('ACCEPT_IF_VALID', ahdl_call), sched_time)
        if dst and Type.is_scalar(ahdl_call.scope.return_type):
            self.emit(AHDL_META('GET_RET_IF_VALID', ahdl_call, dst), sched_time)

        sched_time += 1
        self.emit(AHDL_META('SET_ACCEPT', ahdl_call, 0), sched_time)


    def emit_memload_sequence(self, ahdl_load, sched_time):
        assert ahdl_load.is_a(AHDL_LOAD)
        mem_name = ahdl_load.mem.name()
        memload_latency = 2 #TODO
        self.emit(ahdl_load, sched_time)
        for i in range(1, memload_latency):
            self.emit(AHDL_NOP('wait for output of {}'.format(mem_name)),   sched_time + i)
        self.emit(AHDL_POST_PROCESS(ahdl_load), sched_time + memload_latency)

    def emit_memstore_sequence(self, ahdl_store, sched_time):
        assert ahdl_store.is_a(AHDL_STORE)
        mem_name = ahdl_store.mem.name()
        memstore_latency = 1 #TODO
        self.emit(ahdl_store, sched_time)
        self.emit(AHDL_POST_PROCESS(ahdl_store), sched_time + memstore_latency)

    def emit_array_init_sequence(self, memnode, sched_time):
        if not memnode.is_writable():
            return
        arraynode = memnode.single_source()
        assert arraynode.initstm
        mv = arraynode.initstm
        assert mv.src.is_a(ARRAY)
        memsig = self.scope.gen_sig(memnode.sym.hdl_name(), memnode.width, ['memif'])
        for i, item in enumerate(mv.src.items):
            val = self.translator.visit(item, None) #FIXME
            if val:
                memvar = AHDL_MEMVAR(memsig, memnode, Ctx.STORE)
                store = AHDL_STORE(memvar, val, AHDL_CONST(i))
                self.emit_memstore_sequence(store, sched_time)
                sched_time += 1

    def emit(self, item, sched_time, tag = ''):
        logger.debug('emit '+str(item) + ' at ' + str(sched_time))
        self.scheduled_items.push(sched_time, item, tag)


    def get_signal_prefix(self, ir, node):
        if ir.func_scope.is_class():
            stm = node.tag
            return '{}_{}'.format(stm.dst.sym.name, env.ctor_name)
        elif ir.func_scope.is_method():
            assert ir.func.is_a(ATTR)
            instance_name = self.make_instance_name(ir.func)
            return '{}_{}'.format(instance_name, ir.func.attr.name)
        else:
            assert ir.func.is_a(TEMP)
            return '{}_{}'.format(ir.func_scope.orig_name, node.instance_num)

    def make_instance_name(self, ir):
        assert ir.is_a(ATTR)
        def make_instance_name_rec(ir):
            assert ir.is_a(ATTR)
            if ir.exp.is_a(TEMP):
                if ir.exp.sym.name == env.self_name:
                    if self.scope.is_ctor():
                        return self.scope.parent.orig_name
                    else:
                        return self.scope.orig_name
                else:
                    return ir.exp.sym.hdl_name()
            else:
                instance_name = '{}_{}'.format(make_instance_name_rec(ir.exp), ir.exp.attr.name)
            return instance_name
        return make_instance_name_rec(ir)


class AHDLTranslator:
    def __init__(self, name, host, scope):
        super().__init__()
        self.name = name
        self.host = host
        self.scope = scope
        self.mrg = env.memref_graph

    def reset(self, sched_time):
        self.sched_time = sched_time

    def _emit(self, item, sched_time):
        self.host.emit(item, sched_time)

    def visit_UNOP(self, ir, node):
        exp = self.visit(ir.exp, node)
        return AHDL_OP(ir.op, exp, None)

    def visit_BINOP(self, ir, node):
        left = self.visit(ir.left, node)
        right = self.visit(ir.right, node)
        return AHDL_OP(ir.op, left, right)

    def visit_RELOP(self, ir, node):
        left = self.visit(ir.left, node)
        right = self.visit(ir.right, node)
        return AHDL_OP(ir.op, left, right)

    def _visit_args(self, ir, node):
        callargs = []
        for i, arg in enumerate(ir.args):
            a = self.visit(arg, node)
            callargs.append(a)
        return callargs

    def visit_CALL(self, ir, node):
        if ir.func_scope.is_method():
            instance_name = self.host.make_instance_name(ir.func)
        else:
            instance_name = '{}_{}'.format(ir.func_scope.orig_name, node.instance_num)
        signal_prefix = self.host.get_signal_prefix(ir, node)

        callargs = self._visit_args(ir, node)

        if not ir.func_scope.is_method():
            self.scope.append_callee_instance(ir.func_scope, instance_name)

        ahdl_call = AHDL_MODULECALL(ir.func_scope, callargs, instance_name, signal_prefix)
        return ahdl_call

    def visit_NEW(self, ir, node):
        assert node.tag.is_a(MOVE)
        #assert node.tag.dst.is_a(TEMP)
        mv = node.tag
        if node.tag.dst.is_a(ATTR):
            instance_name = node.tag.dst.attr.hdl_name()
        else:
            instance_name = mv.dst.sym.hdl_name()
        signal_prefix = '{}_{}'.format(instance_name, env.ctor_name)

        callargs = self._visit_args(ir, node)

        self.scope.append_callee_instance(ir.func_scope, instance_name)

        ahdl_call = AHDL_MODULECALL(ir.func_scope, callargs, instance_name, signal_prefix)
        return ahdl_call

    def translate_builtin_len(self, syscall):
        mem = syscall.args[0]
        assert mem.is_a(TEMP)
        memnode = self.mrg.node(mem.sym)
        lens = []
        for source in memnode.sources():
            lens.append(source.length)
        if any(lens[0] != len for len in lens):
            memlensig = self.scope.gen_sig('{}_len'.format(memnode.sym.hdl_name()), -1, ['memif'])
            return AHDL_VAR(memlensig, Ctx.LOAD)
        else:
            assert False # len() must be constant value
        
    def visit_SYSCALL(self, ir, node):
        logger.debug(ir.name)
        if ir.name == 'print':
            fname = '!hdl_print'
        elif ir.name == 'display':
            fname = '!hdl_verilog_display'
        elif ir.name == 'write':
            fname = '!hdl_verilog_write'
        elif ir.name == 'read_reg':
            fname = '!hdl_read_reg'
        elif ir.name == 'write_reg':
            fname = '!hdl_write_reg'
        elif ir.name == 'assert':
            fname = '!hdl_assert'
        elif ir.name == 'len':
            return self.translate_builtin_len(ir)
        else:
            return
        args = []
        for i, arg in enumerate(ir.args):
            a = self.visit(arg, node)
            args.append(a)
        return AHDL_PROCCALL(fname, args)

    def visit_CONST(self, ir, node):
        if ir.value is None:
            return None
        else:
            return AHDL_CONST(ir.value)

    def visit_MREF(self, ir, node):
        offset = self.visit(ir.offset, node)
        memvar = self.visit(ir.mem, node)
        if not memvar.memnode.is_writable():
            return AHDL_FUNCALL(memvar.name(), [offset])
        elif memvar.memnode.is_immutable():
            return AHDL_SUBSCRIPT(memvar, offset)
        else:
            assert isinstance(node.tag, MOVE)
            dst = self.visit(node.tag.dst, node)
            if ir.mem.is_a(ATTR):
                instance_name = self.host.make_instance_name(ir.mem)
                return AHDL_FIELD_LOAD(instance_name, memvar, dst, offset)
            else:
                return AHDL_LOAD(memvar, dst, offset)

    def visit_MSTORE(self, ir, node):
        offset = self.visit(ir.offset, node)
        exp = self.visit(ir.exp, node)
        memvar = self.visit(ir.mem, node)
        assert memvar.memnode.is_writable()
        if ir.mem.is_a(ATTR):
            instance_name = self.host.make_instance_name(ir.mem)
            return AHDL_FIELD_STORE(instance_name, memvar, exp, offset)
        else:
            return AHDL_STORE(memvar, exp, offset)

    def _build_mem_initialize_seq(self, array, memvar, node):
        if array.is_mutable:
            sched_time = self.sched_time
            for i, item in enumerate(array.items):
                if not(isinstance(item, CONST) and item.value is None):
                    store = MSTORE(node.tag.dst, CONST(i), item)
                    ahdl = self.visit(store, node)
                    self.host.emit_memstore_sequence(ahdl, sched_time)
                    sched_time += 1
        else:
            sig = self.scope.gen_sig(array.sym.hdl_name(), 1)
            for i, item in enumerate(array.items):
                idx = AHDL_CONST(i)
                memvar = AHDL_MEMVAR(sig, Type.extra(array.sym.typ), Ctx.STORE)
                ahdl_item = self.visit(item, node)
                ahdl_move = AHDL_MOVE(AHDL_SUBSCRIPT(memvar, idx), ahdl_item)
                self._emit(ahdl_move, self.sched_time)

    def visit_ARRAY(self, ir, node):
        # array expansion
        if not ir.repeat.is_a(CONST):
            print(error_info(ir.lineno))
            raise RuntimeError('multiplier for the sequence must be a constant')
        ir.items = [item.clone() for item in ir.items * ir.repeat.value]

        assert isinstance(node.tag, MOVE)
        ahdl_memvar = self.visit(node.tag.dst, node)
        memnode = ahdl_memvar.memnode

        if not memnode.is_writable():
            return
        arraynode = memnode.single_source()
        assert arraynode.initstm
        mv = arraynode.initstm
        assert mv.src.is_a(ARRAY)
        
        self._build_mem_initialize_seq(ir, ahdl_memvar, node)

    def visit_TEMP(self, ir, node):
        attr = []
        width = -1
        if Type.is_list(ir.sym.typ):
            attr.append('memif')
        elif Type.is_int(ir.sym.typ):
            attr.append('int')
            if ir.ctx & Ctx.STORE:
                attr.append('reg')
            width = INT_WIDTH

        if ir.sym.is_param():
            attr.append('in')
            width = INT_WIDTH
        elif ir.sym.is_return():
            attr.append('out')
            width = INT_WIDTH
        elif ir.sym.is_condition():
            attr.append('cond')
            width = 1

        if self.scope.is_method() and not ir.sym.is_param():
            # a local variable's name in the method is localized
            sig = self.scope.gen_sig('{}_{}'.format(self.scope.orig_name, ir.sym.hdl_name()), width, attr)
        else:
            sig = self.scope.gen_sig(ir.sym.hdl_name(), width, attr)

        if Type.is_seq(ir.sym.typ):
            return AHDL_MEMVAR(sig, Type.extra(ir.sym.typ), ir.ctx)
        else:
            return AHDL_VAR(sig, ir.ctx)

    def visit_ATTR(self, ir, node):
        if Type.is_list(ir.attr.typ):
            sig_attr = ['field', 'memif']
        else:
            sig_attr = ['field', 'int']
        attr = ir.attr.hdl_name()
        if self.scope.is_method() and self.scope.parent is ir.class_scope:
            # internal access to the field
            sig = self.host.gen_sig(ir.class_scope.orig_name + '_field', attr, INT_WIDTH, sig_attr)
        else:
            # external access to the field
            io = '' if ir.ctx == Ctx.LOAD else '_in'
            instance_name = self.host.make_instance_name(ir)
            sig = self.host.gen_sig(instance_name + '_field', attr+io, INT_WIDTH, sig_attr)
        if Type.is_list(ir.attr.typ):
            memnode = self.mrg.node(ir.attr)
            return AHDL_MEMVAR(sig, memnode, ir.ctx)
        else:
            return AHDL_VAR(sig, ir.ctx)

    def visit_EXPR(self, ir, node):
        if not (ir.exp.is_a([CALL, SYSCALL])):
            return

        exp = self.visit(ir.exp, node)
        if exp:
            self._emit(exp, self.sched_time)
        if ir.exp.is_a(CALL):
            latency = get_latency(node.tag)
            self.host.emit_call_ret_sequence(exp, None, latency, self.sched_time)

    def visit_CJUMP(self, ir, node):
        cond = self.visit(ir.exp, node)
        if cond.is_a(AHDL_CONST) and cond.value == 1:
            self._emit(AHDL_TRANSITION(ir.true), self.sched_time)
        else:
            cond_list = [cond, AHDL_CONST(1)]
            codes_list = [[AHDL_TRANSITION(ir.true)], [AHDL_TRANSITION(ir.false)]]
            self._emit(AHDL_TRANSITION_IF(cond_list, codes_list), self.sched_time)

    def visit_JUMP(self, ir, node):
        pass
        #self._emit(AHDL_TRANSITION(ir.target), self.sched_time)

    def visit_MCJUMP(self, ir, node):
        for c, target in zip(ir.conds[:-1], ir.targets[:-1]):
            if c.is_a(CONST) and c.value == 1:
                cond = self.visit(c, node)
                self._emit(AHDL_TRANSITION(target), self.sched_time)
                return

        cond_list = []
        codes_list = []
        for c, target in zip(ir.conds, ir.targets):
            cond = self.visit(c, node)
            cond_list.append(cond)
            codes_list.append([AHDL_TRANSITION(target)])
        self._emit(AHDL_TRANSITION_IF(cond_list, codes_list), self.sched_time)

    def visit_RET(self, ir, node):
        pass

    def _call_proc(self, ir, node):
        src = self.visit(ir.src, node)
        if ir.src.is_a(CALL):
            dst = self.visit(ir.dst, node)
        else:
            dst = None
        latency = get_latency(node.tag)
        self._emit(src, self.sched_time)
        self.host.emit_call_ret_sequence(src, dst, latency, self.sched_time)

    def visit_MOVE(self, ir, node):
        if ir.src.is_a([CALL, NEW]):
            self._call_proc(ir, node)
            return
        elif ir.src.is_a(TEMP) and ir.src.sym.is_param() and ir.src.sym.name.endswith(env.self_name):
            return

        src = self.visit(ir.src, node)
        dst = self.visit(ir.dst, node)
        if not src:
            return
        elif src.is_a(AHDL_STORE):
            self.host.emit_memstore_sequence(src, self.sched_time)
            return
        elif src.is_a(AHDL_LOAD):
            self.host.emit_memload_sequence(src, self.sched_time)
            return

        if dst.is_a(AHDL_MEMVAR) and src.is_a(AHDL_MEMVAR):
            memnode = dst.memnode
            assert memnode
            if ir.src.sym.is_param():
                return
        elif dst.sig.is_field():
            assert ir.dst.is_a(ATTR)
            if dst.is_a(AHDL_VAR):
                if self.scope.is_method():
                    class_name = self.scope.parent.orig_name
                    attr = ir.dst.attr.hdl_name()
                    field_mv = AHDL_FIELD_MOVE(class_name, attr, dst, src, is_ext=False)
                    self.host.emit(field_mv, self.sched_time)
                else:
                    cls = ir.dst.scope.orig_name
                    instance_name = self.host.make_instance_name(ir.dst)
                    attr = ir.dst.attr.hdl_name()
                    field_mv = AHDL_FIELD_MOVE(instance_name, attr, dst, src, is_ext=True)
                    self.host.emit(field_mv, self.sched_time)
                    self.host.emit(AHDL_POST_PROCESS(field_mv), self.sched_time+1)
            return
        
        
        self._emit(AHDL_MOVE(dst, src), self.sched_time)


    def visit_PHI(self, ir, node):
        pass

    def visit_UPHI(self, ir, node):
        assert ir.ps and len(ir.args) == len(ir.ps)
        conds = []
        codes_list = []

        ahdl_dst = self.visit(ir.var, node)
        for arg, p in zip(ir.args, ir.ps):
            conds.append(self.visit(p, node))
            ahdl_src = self.visit(arg, node)
            codes_list.append([AHDL_MOVE(ahdl_dst, ahdl_src)])

        self._emit(AHDL_IF(conds, codes_list), self.sched_time)

    def visit(self, ir, node):
        method = 'visit_' + ir.__class__.__name__
        visitor = getattr(self, method, None)
        return visitor(ir, node)
