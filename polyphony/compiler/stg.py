import sys
from collections import OrderedDict, defaultdict, deque
import functools
from .block import Block
from .ir import *
from .symbol import function_name
from .ahdl import *
from .latency import get_latency
from .common import INT_WIDTH
from .type import Type
from .symbol import Symbol
from .env import env
from logging import getLogger
logger = getLogger(__name__)
import pdb

class State:
    def __init__(self, name, step, codes, transitions, stg):
        assert isinstance(name, str)
        self.name = name
        self.step = step
        self.codes = codes
        self.next_states = []
        self.prev_states = []
        self.transitions = transitions
        self.stg = stg
        self.group = None

    def __str__(self):
        def _strcodes(codes):
            if codes: return ', '.join([str(c) for c in codes])
            else:     return ''
        s = '{}:{}'.format(self.name, self.step)
        if self.codes or self.next_states:
            s += '\n'
            s += "\n".join(['  {}'.format(code) for code in self.codes])
            s += "\n\n  "
            s += ", ".join(['{} => {} <{}>'.format(cond, nstate.name, _strcodes(codes)) for cond, nstate, codes in self.next_states])
            s += "\n"
        else:
            pass
        s += "\n"
        return s

    def __repr__(self):
        return self.name

    def set_next(self, next_data):
        if self.next_states and self.next_states[-1][0] is None and next_data[0] is None:
            logger.debug(self)
            logger.debug(self.next_states)
            assert 0
        if isinstance(next_data[0], AHDL_CONST) and next_data[0].value == 0:
            return
        self.next_states.append(next_data)
        _, nstate, _ = next_data
        nstate.set_prev(self)
        logger.debug('set_next ' + self.name + ' next:' + nstate.name)
        if nstate.step == sys.maxsize:
            nstate.step = self.step + 1
    def replace_next(self, old_state, new_state):
        for i, (cond, nstate, codes) in enumerate(self.next_states):
            if nstate is old_state:
                self.next_states[i] = (cond, new_state, codes)

    def clear_next(self):
        for _, nstate, _ in self.next_states:
            nstate.prev_states.remove(self)
        self.next_states = []

    def set_prev(self, prev):
        self.prev_states.append(prev)

    def resolve_transition(self, next_state, nest=0):
        if next_state:
            logger.debug('\n### resolve_transition {} next: {} nest{}'.format(self.name, next_state.name, nest))
        else:
            logger.debug('\n### resolve_transition {} next: None nest{}'.format(self.name, nest))
        #
        if not self.transitions:
            self.set_next((None, next_state, []))
            return next_state
        
        for t in self.transitions:
            logger.debug('!!! {}'.format(t))
            if t.typ == 'Forward': # forward
                if not next_state:
                    break
                if t.codes:
                    self.set_next((t.cond, next_state, t.codes[:]))
                else:
                    self.set_next((t.cond, next_state, []))
            elif t.typ == 'Finish':# break
                # This stg is a loop section, thus finish_state is the end of the loop section.
                assert not self.stg.is_main()
                self.set_next((t.cond, self.stg.finish_state, []))
            elif t.typ == 'LoopHead':# loop back
                self.set_next((t.cond, self.stg.loop_head, []))
            elif t.typ == 'GroupHead':# continue
                assert t.target_group in self.stg.groups

                group = self.stg.groups[t.target_group]
                assert self not in group.states

                # If the target group is a trunk group, then skip the first state(***_INIT).
                idx = 1 if group.is_trunk else 0
                self.set_next((t.cond, group.states[idx], []))
            elif t.typ == 'Branch':# branch and return
                assert t.target_group in self.stg.groups
                group = self.stg.groups[t.target_group]

                if self not in group.states:
                    idx = 1 if group.is_trunk else 0
                    # my original next_state pass to the last state
                    # of the target group for return from jump
                    jump_group_last_state = group.states[-1]
                    
                    # check same jump target
                    last_state = self.group.states[-1]
                    if last_state.next_states:
                        _, nstate, _ = last_state.next_states[0]
                        if nstate.group is group:
                            continue

                    #assert not last_state.next_states
                    if not jump_group_last_state.next_states:
                        logger.debug('set return state {} to {}'.format(jump_group_last_state.name, next_state.name))
                        jump_group_last_state.resolve_transition(next_state, nest+1)
                    self.set_next((t.cond, group.states[idx], []))
                else:
                    self.set_next((t.cond, next_state, []))
            else:
                assert 0
        self.transitions = []
        return next_state

class StateGroup:
    def __init__(self, name, is_trunk):
        self.name = name
        self.states = []
        self.is_trunk = is_trunk
        self.init_state = None
        self.finish_state = None

    def __str__(self):
        s = ''
        for state in self.states:
            s += str(state)
        return s

    def __repr__(self):
        return self.name

    def __getitem__(self, key):
        return self.states[key]
    
    def __len__(self):
        return len(self.states)

    def append(self, state):
        logger.debug('append {} to group {}'.format(state.name, self.name))
        self.states.append(state)
        state.group = self
    
    def remove(self, state):
        state.group = None
        self.states.remove(state)

class Transition:
    def __init__(self, typ = 'Forward', target = None, cond = None, codes = None):
        assert typ
        self.typ = typ
        self.target_group = target
        self.cond = cond
        self.codes = codes

    def __str__(self):
        return 'Transition {} {} {} {}'.format(self.typ, self.target_group, self.cond, self.codes)

class STG:
    "State Transition Graph"
    def __init__(self, name, parent, states, scope):
        self.name = name
        logger.debug('#### stg ' + name)
        self.parent = parent
        if parent:
            logger.debug('#### parent stg ' + parent.name)
            parent.add_child(self)
        self.groups = OrderedDict()
        self.scope = scope
        self.init_state = None
        self.start_state = None
        self.loop_head = None
        self.finish_state = None
        self.children = []

        if not scope.is_testbench():
            self.ready_sig  = scope.gen_sig('{}_{}'.format(name, 'READY'),  1, ['in', 'ctrl'])
            self.accept_sig = scope.gen_sig('{}_{}'.format(name, 'ACCEPT'), 1, ['in', 'ctrl'])
            self.valid_sig  = scope.gen_sig('{}_{}'.format(name, 'VALID'),  1, ['out', 'ctrl'])

    def __str__(self):
        s = ''
        #for state in self.states:
        #    s += str(state)
        for group in self.groups.values():
            s += str(group)

        return s

    def new_state(self, name, step, codes, transitions):
        return State(name, step, codes, transitions, self)

    def add_child(self, stg):
        self.children.append(stg)

    def is_main(self):
        return not self.parent

    def get_top(self):
        if self.parent:
            return self.parent.get_top()
        else:
            return self

    def get_all_children(self):
        children = self.children
        for c in self.children:
            children.extend(c.get_all_children())
        return children

    def states(self):
        states = []
        for g in self.groups.values():
            states.extend(g.states)
        return states
    
    def remove_state(self, state):
        state.group.remove(state)


class ScheduledItemQueue:
    def __init__(self):
        self.queue = defaultdict(list)

    def push(self, item, sched_time, tag):
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
        self.extra_codes = []
        self.delayed_funcs = None
        self.mrg = env.memref_graph

    def process(self, scope):
        if scope.is_class():
            return
        self.scope = scope
        dfgs = scope.dfgs(bottom_up=False)
        top_dfg = dfgs[0]
        top_stg = self._process_dfg(top_dfg, is_main=True)
        stgs = [top_stg]
        self.dfg2stg[top_dfg] = top_stg

        for dfg in dfgs[1:]:
            stg = self._process_dfg(dfg, is_main=False)
            stgs.append(stg)
            self.dfg2stg[dfg] = stg
        scope.stgs = stgs

    def _get_parent_stg(self, dfg):
        head = dfg.loop_info.head
        parent_block = self.scope.loop_nest_tree.get_parent_of(head)
        assert parent_block
        parent_loop_info = self.scope.loop_infos[parent_block]
        assert parent_loop_info and parent_loop_info.dfg
        return self.dfg2stg[parent_loop_info.dfg]

    def _group_nodes(self, dfg):
        node_groups = defaultdict(list)
        for n in dfg.get_scheduled_nodes():
            if n.begin < 0:
                continue
            if n.is_stm():
                group = n.tag.block.group
            elif n.is_loop():
                group = n.tag.loop_info.head.group
            node_groups[group.name].append(n)

        ordered_node_groups = []
        for gname, nodes in node_groups.items():
            minorder_node = min(nodes, key=lambda n: n.tag.block.order if n.is_stm() else sys.maxsize)
            ordered_node_groups.append((minorder_node.tag.block.order, gname, nodes))
        return sorted(ordered_node_groups)

    def _process_dfg(self, dfg, is_main):
        stg_name = self.scope.orig_name if is_main else '{}'.format(dfg.name)
        self.translator = AHDLTranslator(stg_name, self, self.scope)

        parent_stg = self._get_parent_stg(dfg) if not is_main else None
        self.stg = STG(stg_name, parent_stg, None, self.scope)

        ordered_node_groups = self._group_nodes(dfg)
        for i, (order, gname, nodes) in enumerate(ordered_node_groups):
            state_prefix = stg_name + '_' + gname
            logger.debug('# GROUP ' + state_prefix + ' #')

            is_trunk = True if i == 0 else False
            group = self._process_group_nodes(state_prefix, nodes, dfg, is_main, is_trunk)
            self.stg.groups[state_prefix] = group

        for group in self.stg.groups.values():
            self._resolve_transitions(group, is_main)

        return self.stg


    def _process_group_nodes(self, state_prefix, nodes, dfg, is_main, is_trunk):
        #collect statement and map by scheduled time
        if not nodes:
            return None

        self.scheduled_items = ScheduledItemQueue()
        self._build_scheduled_items(nodes)
        return self._build_state_group(state_prefix, is_main, is_trunk)


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
            if node.is_stm():
                self.translator.visit(node.tag, node)
            elif node.is_loop():
                self.emit(AHDL_META('STG_JUMP', node.tag.name), self.cur_sched_time)
                t = Transition()
                self.emit(t, self.cur_sched_time)


    def _build_state_group(self, state_prefix, is_main, is_trunk):
        '''build State instance one by one, and append to StateGroup'''
        group = StateGroup(state_prefix, is_trunk)
        #add the initial state
        if is_trunk:
            name = '{}_INIT'.format(state_prefix)
            if is_main:
                init_state = self._build_main_init_state(name)
            else:
                init_state = self._build_loop_init_state(name)
            group.append(init_state)
            self.stg.init_state = init_state

        
        last_items = ([], [])
        for step, items in self.scheduled_items.pop():
            codes = []
            transitions = []
            for item, _ in items:
                if isinstance(item, AHDL):
                    codes.append(item)
                elif isinstance(item, Transition):
                    transitions.append(item)
            if step == sys.maxsize:
                last_items = (codes, transitions)
                break
            name = '{}_S{}'.format(state_prefix, step)
            state = self._new_state(name, step+1, codes, transitions)
            group.append(state)

        if is_trunk:
            name = '{}_FINISH'.format(state_prefix)
            if is_main:
                group.finish_state = self._build_main_finish_state(name)
                self.stg.finish_state = group.finish_state
            else:
                group.finish_state = self._build_loop_finish_state(name)
                self.stg.loop_head = group[1]
                self.stg.finish_state = group.finish_state
        elif not is_trunk:
            name = '{}_BRANCH'.format(state_prefix)
            state = self._new_state(name, sys.maxsize, last_items[0], last_items[1])
            group.append(state)
            
        return group


    def _build_main_init_state(self, name):
        if self.scope.is_testbench():
            return self._new_state(name, 0, [], [Transition()])
        cond = AHDL_OP('Eq', AHDL_VAR(self.stg.ready_sig, Ctx.LOAD), AHDL_CONST(1))
        t_codes = [AHDL_MOVE(AHDL_VAR(self.stg.valid_sig, Ctx.STORE), AHDL_CONST(0))]
        #conditional jump to the next state
        t = Transition('Forward', None, cond, t_codes)
        return self._new_state(name, 0, [], [t])

    def _build_main_finish_state(self, name):
        if self.scope.is_testbench():
            return self._new_state(name, sys.maxsize, [], [Transition()])
        cond = AHDL_OP('Eq', AHDL_VAR(self.stg.accept_sig,  Ctx.LOAD), AHDL_CONST(1))
        t = Transition('Forward', None, cond)
        codes = [AHDL_MOVE(AHDL_VAR(self.stg.valid_sig,  Ctx.STORE), AHDL_CONST(1))]
        return self._new_state(name, sys.maxsize, codes, [t])

    def _build_loop_init_state(self, name):
        return self._new_state(name, 0, [], [Transition()])

    def _build_loop_finish_state(self, name):
        return self._new_state(name, sys.maxsize, [], [Transition()])


    def _resolve_transitions(self, group, is_main):
        if group.is_trunk:
            #resolve next state
            assert group.finish_state
            group.append(group.finish_state)
            functools.reduce(lambda s1, s2: s1.resolve_transition(s2), group.states)
            group.finish_state.resolve_transition(group.states[0])
        else:
            #resolve next state
            functools.reduce(lambda s1, s2: s1.resolve_transition(s2), group.states)
            if group[-1].transitions:
                group[-1].resolve_transition(None)


    def gen_sig(self, prefix, postfix, width, attr = None):
        sig = self.scope.gen_sig('{}_{}'.format(prefix, postfix), width, attr)
        return sig

    def _new_state(self, name, step, codes, transitions):
        return self.stg.new_state(name, step, codes, transitions)


    def emit_call_ret_sequence(self, translator, call, node, sched_time):
        stm = node.tag
        assert (stm.is_a(MOVE) and stm.src.is_a([CALL, CTOR])) or (stm.is_a(EXPR) and stm.exp.is_a([CALL, CTOR]))
        signal_prefix = self.get_signal_prefix(call, node)

        code = self._build_call_ready_off(call, node, signal_prefix)
        self.emit(code, sched_time + 1)

        latency = get_latency(node.tag)
        code = self._build_call_ret(translator, call, node, signal_prefix)
        sched_time = sched_time + latency - 1
        while not self.try_emit(code, sched_time, 'call_ret'):
            sched_time += 1
            # This re-scheduling affects any nodes scheduling that after the node
            self.cur_sched_time += 1

        code = self._build_call_accept_off(call, node, signal_prefix)
        sched_time += 1
        self.emit(code, sched_time)

    def _build_call_ready_off(self, call, node, signal_prefix):
        ready = self.scope.gen_sig('{}_{}'.format(signal_prefix, 'READY'), 1, ['reg'])
        return AHDL_MOVE(AHDL_VAR(ready, Ctx.STORE), AHDL_CONST(0))

    def _build_call_ret(self, translator, call, node, signal_prefix):
        stm = node.tag
        has_dst = True if stm.is_a(MOVE) else False

        valid = self.gen_sig(signal_prefix, 'VALID', 1, ['wire'])
        cond = AHDL_OP('Eq', AHDL_VAR(valid, Ctx.LOAD), AHDL_CONST(1))
        #TODO: multiple outputs
        #TODO: bit width
        if Type.is_scalar(call.func_scope.return_type) and has_dst:
            sub_out = self.gen_sig(signal_prefix, 'OUT0', INT_WIDTH, ['wire', 'int'])
            dst = translator.visit(stm.dst, node)
            t_codes = [AHDL_MOVE(dst, AHDL_VAR(sub_out, Ctx.LOAD))]
        else:
            t_codes = []

        call_accept_sig = self.gen_sig(signal_prefix, 'ACCEPT', 1, ['reg'])
        t_codes.append(AHDL_MOVE(AHDL_VAR(call_accept_sig, Ctx.STORE), AHDL_CONST(1)))

        for i, arg in enumerate(call.args):
            if arg.is_a(TEMP) and Type.is_list(arg.sym.typ):
                p, _, _ = call.func_scope.params[i]
                assert Type.is_list(p.typ)
                param_memnode = Type.extra(p.typ)
                if param_memnode.is_joinable() and param_memnode.is_writable():
                    csstr = '{}_{}_{}'.format(signal_prefix, i, arg.sym.hdl_name())
                    cs = self.gen_sig(csstr, 'cs', 1, ['memif'])
                    t_codes.append(AHDL_MOVE(AHDL_VAR(cs, Ctx.STORE), AHDL_CONST(0)))

        #conditional jump to the next state with some codes
        return Transition('Forward', None, cond, t_codes)


    def _build_call_accept_off(self, call, node, signal_prefix):
        accept = self.gen_sig(signal_prefix, 'ACCEPT', 1, ['reg'])
        return AHDL_MOVE(AHDL_VAR(accept, Ctx.STORE), AHDL_CONST(0))


    def emit_memload_sequence(self, dst, src, sched_time):
        assert dst.is_a(AHDL_VAR) and src.is_a(AHDL_MEM)
        mem_name = src.name
        req     = self.gen_sig(mem_name, 'req', -1, ['memif'])
        address = self.gen_sig(mem_name, 'addr', -1, ['memif'])
        we      = self.gen_sig(mem_name, 'we', 1, ['memif'])
        q       = self.gen_sig(mem_name, 'q', -1, ['memif'])
        
        memload_latency = 2 #TODO
        tag_req_on = mem_name + '_req_on'
        tag_req_off = mem_name + '_req_off'
        items = self.scheduled_items.peek(sched_time)
        is_preserve_req = False
        if items:
            for item, tag in items:
                if tag_req_off == tag:
                    is_preserve_req = True
                    items.remove((item, tag))
                    break
        if is_preserve_req:
            self.emit(AHDL_MOVE(AHDL_VAR(address, Ctx.STORE), src.offset), sched_time)
            self.emit(AHDL_MOVE(AHDL_VAR(we, Ctx.STORE), AHDL_CONST(0)),   sched_time)
            for i in range(1, memload_latency):
                self.emit(AHDL_NOP('wait for output of {}'.format(mem_name)),   sched_time + i)
            self.emit(AHDL_MOVE(dst, AHDL_VAR(q, Ctx.LOAD)),              sched_time + memload_latency)
            self.emit(AHDL_MOVE(AHDL_VAR(req, Ctx.STORE), AHDL_CONST(0)),  sched_time + memload_latency + 1, tag_req_off)
        else:
            self.emit(AHDL_MOVE(AHDL_VAR(req, Ctx.STORE), AHDL_CONST(1)),  sched_time, tag_req_on)
            self.emit(AHDL_MOVE(AHDL_VAR(address, Ctx.STORE), src.offset), sched_time)
            self.emit(AHDL_MOVE(AHDL_VAR(we, Ctx.STORE), AHDL_CONST(0)),   sched_time)
            for i in range(1, memload_latency):
                self.emit(AHDL_NOP('wait for output of {}'.format(mem_name)),   sched_time + i)
            self.emit(AHDL_MOVE(dst, AHDL_VAR(q, Ctx.LOAD)),              sched_time + memload_latency)
            self.emit(AHDL_MOVE(AHDL_VAR(req, Ctx.STORE), AHDL_CONST(0)),  sched_time + memload_latency + 1, tag_req_off)


    def emit_memstore_sequence(self, src, sched_time):
        assert src.is_a(AHDL_STORE)
        mem_name = src.mem.name
        req     = self.gen_sig(mem_name, 'req', -1, ['memif'])
        address = self.gen_sig(mem_name, 'addr', -1, ['memif'])
        we      = self.gen_sig(mem_name, 'we', 1, ['memif'])
        d       = self.gen_sig(mem_name, 'd', -1, ['memif'])
        
        memstore_latency = 0 #TODO
        tag_req_on = mem_name + '_req_on'
        tag_req_off = mem_name + '_req_off'
        items = self.scheduled_items.peek(sched_time)
        is_preserve_req = False
        if items:
            for item, tag in items:
                if tag_req_off == tag:
                    is_preserve_req = True
                    items.remove((item, tag))
                    break
        if is_preserve_req:
            self.emit(AHDL_MOVE(AHDL_VAR(address, Ctx.STORE), src.mem.offset), sched_time)
            self.emit(AHDL_MOVE(AHDL_VAR(we, Ctx.STORE), AHDL_CONST(1)),       sched_time)
            self.emit(AHDL_MOVE(AHDL_VAR(d, Ctx.STORE), src.src),              sched_time)
            self.emit(AHDL_MOVE(AHDL_VAR(req, Ctx.STORE), AHDL_CONST(0)),      sched_time + memstore_latency + 1, tag_req_off)
        else:
            self.emit(AHDL_MOVE(AHDL_VAR(req, Ctx.STORE), AHDL_CONST(1)),      sched_time, tag_req_on)
            self.emit(AHDL_MOVE(AHDL_VAR(address, Ctx.STORE), src.mem.offset), sched_time)
            self.emit(AHDL_MOVE(AHDL_VAR(we, Ctx.STORE), AHDL_CONST(1)),       sched_time)
            self.emit(AHDL_MOVE(AHDL_VAR(d, Ctx.STORE), src.src),              sched_time)
            self.emit(AHDL_MOVE(AHDL_VAR(req, Ctx.STORE), AHDL_CONST(0)),      sched_time + memstore_latency + 1, tag_req_off)

    def emit_memswitch(self, memnode, dst, src, sched_time):
        assert src.is_a(AHDL_MEMVAR)
        assert dst.is_a(AHDL_MEMVAR)
        mem_name = dst.memnode.sym.hdl_name()
        # we have to sort them for stable indexing
        preds = sorted(memnode.preds)
        src_node = src.memnode
        assert src_node
        assert src_node in preds
        idx = preds.index(src_node)
        sel = self.gen_sig(mem_name, 'bridge_sel', idx.bit_length(), ['memif'])
        one_hot_mask = bin(1 << idx)[2:]
        self.emit(AHDL_MOVE(AHDL_VAR(sel, Ctx.STORE), AHDL_CONST('\'b'+one_hot_mask)), sched_time)

    def emit_array_init_sequence(self, memnode, sched_time):
        if not memnode.is_writable():
            return
        assert memnode.initstm
        mv = memnode.initstm
        assert mv.src.is_a(ARRAY)
        for i, item in enumerate(mv.src.items):
            val = self.translator.visit(item, None) #FIXME
            if val:
                mem = AHDL_MEM(memnode.sym.hdl_name(), AHDL_CONST(i))
                store = AHDL_STORE(mem, val)
                self.emit_memstore_sequence(store, sched_time)
                sched_time += 1

    def emit(self, item, sched_time, tag = ''):
        logger.debug('emit '+str(item) + ' at ' + str(sched_time))
        self.scheduled_items.push(item, sched_time, tag)

    def try_emit(self, item, sched_time, tag):
        items = self.scheduled_items.peek(sched_time)
        if items:
            items, tags = zip(*items)
            if tag in tags:
                return False
        self.emit(item, sched_time, tag)
        return True

    def get_signal_prefix(self, ir, node):
        if ir.func_scope.is_class():
            stm = node.tag
            return '{}_{}'.format(stm.dst.sym.name, '__init__')
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
            if ir.exp.is_a(TEMP):
                return ir.exp.sym.name
            else:
                assert ir.is_a(ATTR)
                instance_name = '{}_{}'.format(make_instance_name_rec(ir.exp), ir.attr.scope.orig_name)
            return instance_name
        return make_instance_name_rec(ir)

class AHDLTranslator:
    def __init__(self, name, host, scope):
        super().__init__()
        self.name = name
        self.host = host
        self.scope = scope
        self.call_mem_cs = {}
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

    def _visit_args(self, ir, node, instance_name, signal_prefix):
        for i, arg in enumerate(ir.args):
            a = self.visit(arg, node)
            if a.is_a(AHDL_MEMVAR):
                p, _, _ = ir.func_scope.params[i]
                assert Type.is_list(p.typ)
                param_memnode = Type.extra(p.typ)
                if param_memnode.is_joinable() and param_memnode.is_writable():
                    csstr = '{}_{}_{}'.format(instance_name, i, arg.sym.hdl_name())
                    cs = self.host.gen_sig(csstr, 'cs', 1, ['memif'])
                    self._emit(AHDL_MOVE(AHDL_VAR(cs, Ctx.STORE), AHDL_CONST(1)), self.sched_time)
            else:
                if a.is_a(AHDL_VAR):
                    argsig = self.scope.gen_sig('{}_IN{}'.format(signal_prefix, i), INT_WIDTH, ['int'])
                else:
                    argsig = self.scope.gen_sig('{}_IN{}'.format(signal_prefix, i), INT_WIDTH, ['int'])
                self._emit(AHDL_MOVE(AHDL_VAR(argsig, Ctx.STORE), a), self.sched_time)

    def visit_CALL(self, ir, node):
        if ir.func_scope.is_method():
            instance_name = self.host.make_instance_name(ir.func)
        else:
            instance_name = '{}_{}'.format(ir.func_scope.orig_name, node.instance_num)
        signal_prefix = self.host.get_signal_prefix(ir, node)

        self._visit_args(ir, node, instance_name, signal_prefix)

        ready = self.host.gen_sig(signal_prefix, 'READY', 1)
        self._emit(AHDL_MOVE(AHDL_VAR(ready, Ctx.STORE), AHDL_CONST(1)), self.sched_time)

        #TODO: should call on the resource allocator
        if not ir.func_scope.is_method():
            self.scope.append_call(ir.func_scope, instance_name)

        return None

    def visit_CTOR(self, ir, node):
        assert node.tag.is_a(MOVE)
        assert node.tag.dst.is_a(TEMP)
        mv = node.tag
        instance_name = mv.dst.sym.name
        signal_prefix = '{}_{}'.format(instance_name, '__init__')

        self._visit_args(ir, node, instance_name, signal_prefix)

        ready = self.host.gen_sig(signal_prefix, 'READY', 1)
        self._emit(AHDL_MOVE(AHDL_VAR(ready, Ctx.STORE), AHDL_CONST(1)), self.sched_time)

        self.scope.append_call(ir.func_scope, instance_name)

        return None

    def translate_builtin_len(self, syscall):
        mem = syscall.args[0]
        assert mem.is_a(TEMP)
        memnode = self.mrg.node(mem.sym)
        lens = []
        for root in self.mrg.collect_node_roots(memnode):
            lens.append(root.length)
        if any(lens[0] != len for len in lens):
            memlensig = self.scope.gen_sig('{}_len'.format(memnode.sym.hdl_name()), -1, ['memif'])
            return AHDL_VAR(memlensig, Ctx.LOAD)
        else:
            assert False # len() must be constant value
        
    def visit_SYSCALL(self, ir, node):
        logger.debug(ir.name)
        if ir.name == 'print':
            fname = '!hdl_print'
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
        if ir.mem.is_a(TEMP):
            memsym = ir.mem.sym
        elif ir.mem.is_a(ATTR):
            memsym = ir.mem.attr
        if Type.is_list(memsym.typ):
            memnode = self.mrg.node(memsym)
            if not memnode.is_writable():
                return AHDL_FUNCALL(memsym.hdl_name(), [offset])
            else:
                if ir.mem.is_a(ATTR):
                    instance_name = self.host.make_instance_name(ir.mem)
                    return AHDL_MEM('{}_{}'.format(instance_name, memsym.ancestor.hdl_name()), offset)
                else:
                    return AHDL_MEM(memsym.hdl_name(), offset)
        else:
            # TODO
            return None
            
    def visit_MSTORE(self, ir, node):
        offset = self.visit(ir.offset, node)
        exp = self.visit(ir.exp, node)
        if ir.mem.is_a(TEMP):
            memsym = ir.mem.sym
        elif ir.mem.is_a(ATTR):
            memsym = ir.mem.attr
        assert self.mrg.node(memsym).is_writable()
        mem = AHDL_MEM(memsym.hdl_name(), offset)
        return AHDL_STORE(mem, exp)

    def visit_ARRAY(self, ir, node):
        return ir

    def visit_TEMP(self, ir, node):
        attr = []
        width = -1
        if Type.is_list(ir.sym.typ):
            return AHDL_MEMVAR(Type.extra(ir.sym.typ), ir.ctx)
        elif Type.is_int(ir.sym.typ):
            attr.append('int')
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
        return AHDL_VAR(sig, ir.ctx)

    def visit_ATTR(self, ir, node):
        attr = ir.attr.hdl_name()
        if self.scope.is_method() and self.scope.parent is ir.scope:
            # internal access to the field
            sig = self.host.gen_sig('field', attr, INT_WIDTH, ['field'])
        else:
            # external access to the field
            io = '' if ir.ctx == Ctx.LOAD else '_IN'
            instance_name = self.host.make_instance_name(ir)
            sig = self.host.gen_sig(instance_name, attr+io, INT_WIDTH, ['field'])
        #sym.typ = ir.attr.typ
        return AHDL_VAR(sig, ir.ctx)

    def visit_EXPR(self, ir, node):
        if not (ir.exp.is_a([CALL, SYSCALL])):
            return
        if ir.exp.is_a(CALL):
            self.host.emit_call_ret_sequence(self, ir.exp, node, self.sched_time)

        exp = self.visit(ir.exp, node)
        if exp:
            self._emit(exp, self.sched_time)

    def visit_PARAM(self, ir, node):
        pass

    def visit_CJUMP(self, ir, node):
        assert ir.true is ir.true.group.blocks[0]
        #if ir.true is not ir.true.group.blocks[0]:
        #    print(ir.true)
        #    assert 0
        cond = self.visit(ir.exp, node)
        true_grp = self.host.stg.name + '_' + ir.true.group.name
                    
        t = Transition('Branch', true_grp, cond)
        self._emit(t, self.sched_time)
        if cond.is_a(AHDL_CONST) and cond.value == 1:
            return

        cond = AHDL_CONST(1)
        # In case of explicit else target
        if ir.false is ir.false.group.blocks[0]:
            false_grp = self.host.stg.name + '_' + ir.false.group.name
            t = Transition('Branch', false_grp, cond)
            self._emit(t, self.sched_time)
        # In case of implicit else target (no 'else' if-statement)
        else:
            #through to the next state in the same group
            t = Transition()
            self._emit(t, self.sched_time)

    def visit_JUMP(self, ir, node):
        #These jumps are put into the last state of the group
        sched = -1
        if ir.typ == 'B':
            typ = 'Finish'
            target_grp = None
        elif ir.typ == 'L':
            typ = 'LoopHead'
            target_grp = None
        elif ir.typ == 'C':
            typ = 'GroupHead'
            assert ir.target is ir.target.group.blocks[0]
            target_grp = self.host.stg.name + '_' + ir.target.group.name
        elif ir.typ == 'E':
            typ = 'Forward'
            target_grp = None
            self._emit(AHDL_META('STG_EXIT'), self.sched_time)
        else:
            assert 0
        t = Transition(typ, target_grp)
        self._emit(t, sched)

    def visit_MCJUMP(self, ir, node):
        for c, tgt in zip(ir.conds[:-1], ir.targets[:-1]):
            if c.is_a(CONST) and c.value == 1:
                cond = self.visit(c, node)
                target_grp = self.host.stg.name + '_' + tgt.group.name
                t = Transition('Branch', target_grp, cond)
                self._emit(t, self.sched_time)
                return

        for c, target in zip(ir.conds, ir.targets):
            cond = self.visit(c, node)
            target_grp = self.host.stg.name + '_' + target.group.name
            if c.is_a(CONST) and c is ir.conds[-1]:
                # In case of explicit else target
                if target is target.group.blocks[0]:
                    t = Transition('Branch', target_grp, cond)
                # In case of implicit else target (no 'else' if-statement)
                else:
                    #through to the next state in the same group
                    t = Transition()
            else:
                t = Transition('Branch', target_grp, cond)
            self._emit(t, self.sched_time)

    def visit_RET(self, ir, node):
        pass

    def visit_MOVE(self, ir, node):
        if ir.src.is_a([CALL, CTOR]):
            self.host.emit_call_ret_sequence(self, ir.src, node, self.sched_time)
        elif ir.src.is_a(TEMP) and ir.src.sym.is_param() and ir.src.sym.name.endswith('self'):
            return
        elif ir.src.is_a(ARRAY):
            if ir.dst.is_a(TEMP):
                memsym = ir.dst.sym
            elif ir.dst.is_a(ATTR):
                memsym = ir.dst.attr
            memnode = self.mrg.node(memsym)
            self.host.emit_array_init_sequence(memnode, self.sched_time)
            return

        src = self.visit(ir.src, node)
        dst = self.visit(ir.dst, node)
        if dst.is_a(AHDL_MEMVAR) and src.is_a(AHDL_MEMVAR):
            memnode = dst.memnode
            assert memnode
            if ir.src.sym.is_param():
                return
            if memnode.is_joinable():
                self.host.emit_memswitch(memnode, dst, src, self.sched_time)
                return
        elif dst.is_a(AHDL_VAR) and dst.sig.is_field() and not self.scope.is_method():
            assert ir.dst.is_a(ATTR)
            cls = ir.dst.scope.orig_name
            instance_name = self.host.make_instance_name(ir.dst) # instance_name = '{}_{}'.format(cls, node.instance_num)
            attr = ir.dst.attr.hdl_name()
            field_ready = self.host.gen_sig(instance_name, attr+'_READY', 1)
            self._emit(AHDL_MOVE(AHDL_VAR(field_ready, Ctx.STORE), AHDL_CONST(1)), self.sched_time)
            self._emit(AHDL_MOVE(AHDL_VAR(field_ready, Ctx.STORE), AHDL_CONST(0)), self.sched_time+1)
        if src:
            if src.is_a(AHDL_STORE):
                self.host.emit_memstore_sequence(src, self.sched_time)
                return
            elif src.is_a(AHDL_MEM):
                self.host.emit_memload_sequence(dst, src, self.sched_time)
                return
            self._emit(AHDL_MOVE(dst, src), self.sched_time)
    def visit_PHI(self, ir, node):
        pass

    def visit(self, ir, node):
        method = 'visit_' + ir.__class__.__name__
        visitor = getattr(self, method, None)
        return visitor(ir, node)
