import sys
from collections import OrderedDict, defaultdict
import functools
from .block import Block
from .ir import *
from .ahdl import *
from .common import error_info
from .env import env
from .memref import *
from logging import getLogger
logger = getLogger(__name__)


class State(object):
    def __init__(self, name, step, codes, stg):
        assert isinstance(name, str)
        self.name = name
        self.step = step
        self.codes = codes
        self.stg = stg

    def __str__(self):
        s = '---------------------------------\n'
        s += '{}:{}\n'.format(self.name, self.step)
        if self.codes:
            if self.codes:
                strcodes = ''.join(['{}\n'.format(code) for code in self.codes])
                lines = strcodes.split('\n')
                s += '\n'.join(['  {}'.format(line) for line in lines])
        else:
            pass
        s += '\n'
        return s

    def __repr__(self):
        return self.name

    def resolve_transition(self, next_state):
        code = self.codes[-1]
        if code.is_a(AHDL_TRANSITION):
            if code.target is None:
                code.target = next_state
            else:
                assert isinstance(code.target, Block)
                code.target = self.stg.scope.blk2state[code.target][0]
            transition = code
        elif code.is_a(AHDL_TRANSITION_IF):
            for i, codes in enumerate(code.codes_list):
                assert len(codes) == 1
                transition = codes[0]
                assert transition.is_a(AHDL_TRANSITION)
                assert isinstance(transition.target, Block)
                target_state = self.stg.scope.blk2state[transition.target][0]
                transition.target = target_state
            transition = code
        else:
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


class STG(object):
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
        self.mrg = env.memref_graph

    def process(self, scope):
        if scope.is_global() or scope.is_class() or scope.is_lib():
            return
        self.scope = scope
        self.scope.blk2state = {}
        stgs = []
        dfgs = scope.dfgs(bottom_up=False)
        for i, dfg in enumerate(dfgs):
            stg = self._process_dfg(i, dfg)
            stgs.append(stg)
            self.dfg2stg[dfg] = stg

        main_stg = stgs[0]
        functools.reduce(lambda s1, s2: s1.resolve_transition(s2), main_stg.states)
        if scope.is_worker() or scope.is_testbench():
            main_stg.states[-1].resolve_transition(main_stg.states[-1])
        else:
            main_stg.states[-1].resolve_transition(main_stg.states[0])
        for stg in stgs[1:]:
            functools.reduce(lambda s1, s2: s1.resolve_transition(s2), stg.states)
            stg.states[-1].resolve_transition(stg.states[0])

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
        if self.scope.parent and self.scope.parent.is_module() and self.scope.is_callable():
            if is_main:
                stg_name = self.scope.parent.orig_name
            else:
                stg_name = '{}_L{}'.format(self.scope.parent.orig_name, index)
        else:
            if is_main:
                stg_name = self.scope.orig_name
            else:
                stg_name = '{}_L{}'.format(self.scope.orig_name, index)
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
            is_last = True if i == len(dfg.blocks) - 1 else False

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
        self.cur_sched_time = 0
        for delta, nodes in scheduled_node_list:
            self.cur_sched_time += delta
            self._translate_nodes(nodes)

    def _translate_nodes(self, nodes):
        '''translates IR to AHDL or Transition, and emit to scheduled_items'''
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
            state = self._new_state(name, step + 1, codes)
            states.append(state)
        if not states:
            name = '{}_S{}'.format(state_prefix, 0)
            codes = [AHDL_TRANSITION(None)]
            states = [self._new_state(name, 1, codes)]

        if blk.stms[-1].is_a(JUMP):
            jump = blk.stms[-1]
            last_state = states[-1]
            trans = last_state.codes[-1]
            assert trans.is_a([AHDL_TRANSITION, AHDL_META_WAIT])
            if trans.is_a(AHDL_TRANSITION):
                trans.target = jump.target

        # deal with the first/last state
        if not is_main:
            if is_first:
                self.stg.init_state = states[0]
            if is_last:
                self.stg.finish_state = states[0]
        elif self.scope.is_worker() or self.scope.is_testbench():
            if is_first:
                name = '{}_INIT'.format(state_prefix)
                init_state = states[0]
                init_state.name = name
                assert init_state.codes[-1].is_a([AHDL_TRANSITION,
                                                  AHDL_TRANSITION_IF,
                                                  AHDL_META_WAIT])
                self.stg.init_state = init_state
            if is_last:
                last_state = states[-1]
                if self.scope.is_worker():
                    codes = [AHDL_TRANSITION(None)]
                elif self.scope.is_testbench():
                    codes = [
                        AHDL_INLINE('$display("%5t:finish", $time)'),
                        AHDL_INLINE('$finish()')
                    ]
                finish_state = self._new_state('{}_FINISH'.format(state_prefix),
                                               last_state.step + 1,
                                               codes)
                states.append(finish_state)
                self.stg.finish_state = finish_state
        else:
            if is_first:
                first_state = states[0]
                assert first_state.codes[-1].is_a([AHDL_TRANSITION, AHDL_TRANSITION_IF])
                if not (len(states) <= 1 and is_last):
                    prolog = AHDL_SEQ(AHDL_CALLEE_PROLOG(self.stg.name), 0, 1)
                    init_state = self._new_state('{}_INIT'.format(state_prefix),
                                                 0,
                                                 [prolog, AHDL_TRANSITION(None)])
                    states.insert(0, init_state)
                self.stg.init_state = states[0]
            if is_last:
                name = '{}_FINISH'.format(state_prefix)
                finish_state = states[-1]
                finish_state.name = name
                assert finish_state.codes[-1].is_a(AHDL_TRANSITION)
                epilog = AHDL_SEQ(AHDL_CALLEE_EPILOG(self.stg.name), 0, 1)
                finish_state.codes.insert(-1, epilog)
                self.stg.finish_state = finish_state
        return states

    def gen_sig(self, prefix, postfix, width, tag=None):
        sig = self.scope.gen_sig('{}_{}'.format(prefix, postfix), width, tag)
        return sig

    def _new_state(self, name, step, codes):
        return self.stg.new_state(name, step, codes)

    def emit_call_sequence(self, ahdl_call, dst, node, sched_time):
        assert ahdl_call.is_a(AHDL_MODULECALL)
        # TODO:
        if dst:
            ahdl_call.returns = [dst]
        else:
            ahdl_call.returns = []
        step_n = node.latency()
        for i in range(step_n):
            self.emit(AHDL_SEQ(ahdl_call, i, step_n), sched_time + i)

    def emit_memload_sequence(self, ahdl_load, sched_time):
        assert ahdl_load.is_a(AHDL_LOAD)
        step_n = 3  # TODO : It should calculate from a memory type
        for i in range(step_n):
            self.emit(AHDL_SEQ(ahdl_load, i, step_n), sched_time + i)

    def emit_memstore_sequence(self, ahdl_store, sched_time):
        assert ahdl_store.is_a(AHDL_STORE)
        step_n = 2  # TODO : It should calculate from a memory type
        for i in range(step_n):
            self.emit(AHDL_SEQ(ahdl_store, i, step_n), sched_time + i)

    def emit(self, item, sched_time, tag=''):
        logger.debug('emit ' + str(item) + ' at ' + str(sched_time))
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


class AHDLTranslator(object):
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
        return AHDL_OP(ir.op, exp)

    def visit_BINOP(self, ir, node):
        left = self.visit(ir.left, node)
        right = self.visit(ir.right, node)
        return AHDL_OP(ir.op, left, right)

    def visit_RELOP(self, ir, node):
        left = self.visit(ir.left, node)
        right = self.visit(ir.right, node)
        return AHDL_OP(ir.op, left, right)

    def visit_CONDOP(self, ir, node):
        cond = self.visit(ir.cond, node)
        left = self.visit(ir.left, node)
        right = self.visit(ir.right, node)
        return AHDL_IF_EXP(cond, left, right)

    def _visit_args(self, ir, node):
        callargs = []
        for i, (_, arg) in enumerate(ir.args):
            a = self.visit(arg, node)
            callargs.append(a)
        return callargs

    def visit_CALL(self, ir, node):
        if ir.func_scope.is_method():
            if ir.func_scope.parent.is_module():
                print(error_info(self.scope, ir.lineno))
                raise RuntimeError("It is only supported calling run() of @top decorated class")
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
        _, mem = syscall.args[0]
        assert mem.is_a(TEMP)
        memnode = self.mrg.node(mem.sym)
        lens = []
        for source in memnode.sources():
            lens.append(source.length)
        if any(lens[0] != len for len in lens):
            memlensig = self.scope.gen_sig('{}_len'.format(memnode.sym.hdl_name()), -1, ['memif'])
            return AHDL_VAR(memlensig, Ctx.LOAD)
        else:
            assert False  # len() must be constant value

    def visit_SYSCALL(self, ir, node):
        syscall_name = ir.sym.name
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
        elif ir.sym.name == 'polyphony.timing.clksleep':
            _, cycle = ir.args[0]
            assert cycle.is_a(CONST)
            for i in range(cycle.value):
                self.host.emit(AHDL_NOP('wait a cycle'), self.sched_time + i)
            return
        elif ir.sym.name == 'polyphony.timing.wait_rising':
            ports = []
            for _, a in ir.args:
                assert a.is_a([TEMP, ATTR])
                port_sig = self._port_sig(a.qualified_symbol())
                ports.append(AHDL_VAR(port_sig, Ctx.LOAD))
            self._emit(AHDL_META_WAIT('WAIT_EDGE', AHDL_CONST(0), AHDL_CONST(1), *ports), self.sched_time)
            return
        elif ir.sym.name == 'polyphony.timing.wait_falling':
            ports = []
            for _, a in ir.args:
                assert a.is_a([TEMP, ATTR])
                port_sig = self._port_sig(a.qualified_symbol())
                ports.append(AHDL_VAR(port_sig, Ctx.LOAD))
            self._emit(AHDL_META_WAIT('WAIT_EDGE', AHDL_CONST(1), AHDL_CONST(0), *ports), self.sched_time)
            return
        elif ir.sym.name == 'polyphony.timing.wait_edge':
            ports = []
            _, _old = ir.args[0]
            _, _new = ir.args[1]
            old = self.visit(_old, node)
            new = self.visit(_new, node)
            for _, a in ir.args[2:]:
                assert a.is_a([TEMP, ATTR])
                port_sig = self._port_sig(a.qualified_symbol())
                ports.append(AHDL_VAR(port_sig, Ctx.LOAD))
            self._emit(AHDL_META_WAIT('WAIT_EDGE', old, new, *ports), self.sched_time)
            return
        elif ir.sym.name == 'polyphony.timing.wait_value':
            ports = []
            _, _val = ir.args[0]
            value = self.visit(_val, node)
            for _, a in ir.args[1:]:
                assert a.is_a([TEMP, ATTR])
                port_sig = self._port_sig(a.qualified_symbol())
                ports.append(AHDL_VAR(port_sig, Ctx.LOAD))
            self._emit(AHDL_META_WAIT('WAIT_VALUE', value, *ports), self.sched_time)
            return
        else:
            # TODO: user-defined builtins
            return
        args = []
        for i, (_, arg) in enumerate(ir.args):
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
            return AHDL_FUNCALL(AHDL_SYMBOL(memvar.name()), [offset])
        elif memvar.memnode.is_immutable():
            return AHDL_SUBSCRIPT(memvar, offset)
        else:
            assert isinstance(node.tag, MOVE)
            dst = self.visit(node.tag.dst, node)
            return AHDL_LOAD(memvar, dst, offset)

    def visit_MSTORE(self, ir, node):
        offset = self.visit(ir.offset, node)
        exp = self.visit(ir.exp, node)
        memvar = self.visit(ir.mem, node)
        memvar.ctx = Ctx.STORE
        assert memvar.memnode.is_writable()
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
            sig = self.scope.gen_sig(array.sym.hdl_name(), 1, {'memif'})
            for i, item in enumerate(array.items):
                idx = AHDL_CONST(i)
                memvar = AHDL_MEMVAR(sig, array.sym.typ.get_memnode(), Ctx.STORE)
                ahdl_item = self.visit(item, node)
                ahdl_move = AHDL_MOVE(AHDL_SUBSCRIPT(memvar, idx), ahdl_item)
                self._emit(ahdl_move, self.sched_time)

    def visit_ARRAY(self, ir, node):
        # array expansion
        if not ir.repeat.is_a(CONST):
            print(error_info(self.scope, ir.lineno))
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

    def _signal_width(self, sym):
        width = -1
        if sym.typ.is_seq():
            width = sym.typ.get_element().get_width()
        elif sym.typ.is_int() or sym.typ.is_bool():
            width = sym.typ.get_width()
        elif sym.typ.is_port():
            width = sym.typ.get_width()
        elif sym.is_condition():
            width = 1
        return width

    def _sym_2_sig(self, sym, ctx):
        tags = set()
        if sym.typ.is_seq():
            if sym.typ.is_list():
                tags.add('memif')
        elif sym.typ.is_int() or sym.typ.is_bool():
            if sym.typ.has_signed() and sym.typ.get_signed():
                tags.add('int')
            else:
                pass
            if ctx & Ctx.STORE:
                tags.add('reg')
        elif sym.typ.is_port():
            di = sym.typ.get_direction()
            assert di != '?'
            if di != 'inout':
                tags.add(di)

        if sym.is_param():
            tags.add('input')
        elif sym.is_return():
            tags.add('output')
        elif sym.is_condition():
            tags.add('condition')
        if sym.is_alias():
            tags.discard('reg')
            tags.add('net')

        if self.scope.is_worker() or self.scope.is_method():
            sig_name = '{}_{}'.format(self.scope.orig_name, sym.hdl_name())
        elif 'input' in tags:
            sig_name = '{}_{}'.format(self.scope.orig_name, sym.hdl_name())
        elif 'output' in tags:
            sig_name = '{}_out_0'.format(self.scope.orig_name)
        else:
            sig_name = sym.hdl_name()

        width = self._signal_width(sym)
        sig = self.scope.gen_sig(sig_name, width, tags)
        return sig

    def visit_TEMP(self, ir, node):
        sig = self._sym_2_sig(ir.sym, ir.ctx)
        if ir.sym.typ.is_seq():
            return AHDL_MEMVAR(sig, ir.sym.typ.get_memnode(), ir.ctx)
        else:
            return AHDL_VAR(sig, ir.ctx)

    def visit_ATTR(self, ir, node):
        if ir.attr.typ.is_list():
            sig_tags = {'field', 'memif'}
        else:
            sig_tags = {'field', 'int'}
        attr = ir.attr.hdl_name()
        if self.scope.parent.is_module():
            sym = ir.symbol().ancestor if ir.symbol().ancestor else ir.symbol()
            signame = sym.hdl_name()
            width = self._signal_width(sym)
            sig = self.scope.gen_sig(signame, width, sig_tags)
        elif self.scope.is_method() and self.scope.parent is ir.attr_scope:
            # internal access to the field
            width = self._signal_width(ir.attr)
            sig = self.host.gen_sig(ir.attr_scope.orig_name + '_field', attr, width, sig_tags)
        else:
            # external access to the field
            io = '' if ir.ctx == Ctx.LOAD else '_in'
            instance_name = self.host.make_instance_name(ir)
            width = self._signal_width(ir.attr)
            sig = self.host.gen_sig(instance_name + '_field', attr + io, width, sig_tags)
        if ir.attr.typ.is_list():
            memnode = self.mrg.node(ir.attr)
            return AHDL_MEMVAR(sig, memnode, ir.ctx)
        else:
            return AHDL_VAR(sig, ir.ctx)

    def visit_EXPR(self, ir, node):
        if not (ir.exp.is_a([CALL, SYSCALL])):
            return

        if self._is_port_method(ir.exp):
            return self._make_port_access(ir.exp, None, node)
        elif self._is_module_method(ir.exp):
            return
        if ir.exp.is_a(CALL):
            self._call_proc(ir, node)
        else:
            exp = self.visit(ir.exp, node)
            if exp:
                self._emit(exp, self.sched_time)

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
        if ir.is_a(MOVE):
            call = ir.src
        elif ir.is_a(EXPR):
            call = ir.exp

        ahdl_call = self.visit(call, node)
        if call.is_a(CALL) and ir.is_a(MOVE):
            dst = self.visit(ir.dst, node)
        else:
            dst = None
        if ir.is_a(MOVE) and ir.src.is_a([NEW, CALL]) and ir.src.func_scope.is_module():
            return
        self.host.emit_call_sequence(ahdl_call, dst, node, self.sched_time)

        params = ahdl_call.scope.params
        for arg, param in zip(ahdl_call.args, params):
            p, _, _ = param
            if arg.is_a(AHDL_MEMVAR):
                assert p.typ.is_seq()
                param_memnode = p.typ.get_memnode()
                # find joint node in outer scope
                assert len(param_memnode.preds) == 1
                is_joinable_param = isinstance(param_memnode.preds[0], N2OneMemNode)
                if is_joinable_param and param_memnode.is_writable():
                    self._emit(AHDL_META('MEM_SWITCH',
                                         ahdl_call.instance_name,
                                         param_memnode,
                                         arg.memnode), self.sched_time)

    def visit_MOVE(self, ir, node):
        if ir.src.is_a([CALL, NEW]):
            if self._is_port_method(ir.src):
                return self._make_port_access(ir.src, ir.dst, node)
            elif self._is_port_ctor(ir.src):
                return self._make_port_init(ir.src, ir.dst, node)
            elif self._is_module_method(ir.src):
                return
            self._call_proc(ir, node)
            return
        elif ir.src.is_a(TEMP) and ir.src.sym.is_param():
            if ir.src.sym.name.endswith(env.self_name):
                return
            elif ir.src.sym.typ.is_object() and ir.src.sym.typ.get_scope().is_module():
                return
            elif ir.src.sym.typ.is_port():
                return
        src = self.visit(ir.src, node)
        dst = self.visit(ir.dst, node)
        if not src:
            return
        elif src.is_a(AHDL_VAR) and dst.is_a(AHDL_VAR) and src.sig == dst.sig:
            return
        elif src.is_a(AHDL_STORE):
            self.host.emit_memstore_sequence(src, self.sched_time)
            return
        elif src.is_a(AHDL_LOAD):
            self.host.emit_memload_sequence(src, self.sched_time)
            return
        elif dst.is_a(AHDL_MEMVAR) and src.is_a(AHDL_MEMVAR):
            memnode = dst.memnode
            assert memnode
            if ir.src.sym.is_param():
                return
            elif memnode.is_immutable():
                return
            elif memnode.is_joinable():
                self._emit(AHDL_META('MEM_SWITCH', '', dst.memnode, src.memnode), self.sched_time)
                return
        self._emit(AHDL_MOVE(dst, src), self.sched_time)

    def visit_PHI(self, ir, node):
        pass

    def visit_UPHI(self, ir, node):
        assert ir.ps and len(ir.args) == len(ir.ps) and len(ir.args) > 1
        ahdl_dst = self.visit(ir.var, node)
        arg_p = list(zip(ir.args, ir.ps))
        rexp, cond = arg_p[-1]
        cond = self.visit(cond, node)
        if cond.is_a(CONST) and cond.value:
            rexp = self.visit(rexp, node)
        else:
            lexp = self.visit(rexp, node)
            rexp = AHDL_IF_EXP(cond, lexp, AHDL_SYMBOL("'bz"))
        for arg, p in arg_p[-2::-1]:
            lexp = self.visit(arg, node)
            cond = self.visit(p, node)
            if_exp = AHDL_IF_EXP(cond, lexp, rexp)
            rexp = if_exp
        self._emit(AHDL_MOVE(ahdl_dst, if_exp), self.sched_time)

    def visit(self, ir, node):
        method = 'visit_' + ir.__class__.__name__
        visitor = getattr(self, method, None)
        return visitor(ir, node)

    def _is_port_method(self, ir):
        return ir.is_a(CALL) and ir.func_scope.is_method() and ir.func_scope.parent.is_port()

    def _is_port_ctor(self, ir):
        return ir.is_a(NEW) and ir.func_scope.is_port()

    def _port_sig(self, port_qsym):
        assert port_qsym[-1].typ.is_port()
        port_sym = port_qsym[-1]
        root_sym = port_sym.typ.get_root_symbol()
        port_prefixes = port_qsym[:-1] + (root_sym,)

        if port_prefixes[0].name == env.self_name:
            port_prefixes = port_prefixes[1:]
        port_name = '_'.join([pfx.hdl_name() for pfx in port_prefixes])

        port_sig = port_sym.scope.signal(port_name)
        if port_sig:
            return port_sig

        dtype = port_sym.typ.get_dtype()
        width = dtype.get_width()
        port_scope = port_sym.typ.get_scope()
        tags = set()
        if port_scope.orig_name.startswith('Port'):
            tags.add('single_port')
            if dtype.has_signed() and dtype.get_signed():
                tags.add('int')
        elif port_scope.orig_name.startswith('Queue'):
            # TODO
            tags.add('fifo_port')
            tags.add('seq_port')
        direction = port_sym.typ.get_direction()
        assert direction != '?'
        protocol = port_sym.typ.get_protocol()
        kind = port_sym.typ.get_port_kind()

        if kind == 'internal':
            if 'seq_port' in tags:
                pass  # tag?
            else:
                tags.add('reg')
        elif self.scope.parent.is_subclassof(port_sym.scope) and port_sym.scope.is_module():
            if direction != 'inout':
                tags.add(direction)
        elif self.scope.is_worker():
            if direction != 'inout':
                tags.add(direction)
        else:
            # TODO
            tags.add('extport')
            if direction == 'input':
                tags.add('reg')
            elif direction == 'output':
                tags.add('net')
            else:
                assert False

        if protocol != 'none':
            tags.add(protocol + '_protocol')
        if 'extport' in tags:
            port_sig = self.scope.gen_sig(port_name, width, tags)
        else:
            if root_sym.scope.is_module():
                module_scope = root_sym.scope
            elif root_sym.scope.is_ctor() and root_sym.scope.parent.is_module():
                module_scope = root_sym.scope.parent
            else:
                assert False
            port_sig = module_scope.gen_sig(port_name, width, tags)

        if port_sym.typ.has_init():
            tags.add('initializable')
            port_sig.init_value = port_sym.typ.get_init()
        if port_sym.typ.has_maxsize():
            port_sig.maxsize = port_sym.typ.get_maxsize()
        return port_sig

    def _make_port_access(self, call, target, node):
        assert call.func.is_a(ATTR)
        port_qsym = call.func.qualified_symbol()[:-1]
        port_sig = self._port_sig(port_qsym)

        if call.func_scope.orig_name == 'wr':
            self._make_port_write_seq(call, port_sig, node)
        elif call.func_scope.orig_name == 'rd':
            self._make_port_read_seq(target, port_sig, node)
        else:
            assert False

    def _make_port_write_seq(self, call, port_sig, node):
        assert call.args
        _, val = call.args[0]
        src = self.visit(val, node)
        iow = AHDL_IO_WRITE(AHDL_VAR(port_sig, Ctx.STORE),
                            src,
                            port_sig.is_output())
        step_n = node.latency()
        for i in range(step_n):
            self._emit(AHDL_SEQ(iow, i, step_n), self.sched_time + i)
        return

    def _make_port_read_seq(self, target, port_sig, node):
        assert target
        dst = self.visit(target, node)
        ior = AHDL_IO_READ(AHDL_VAR(port_sig, Ctx.LOAD),
                           dst,
                           port_sig.is_input())
        step_n = node.latency()
        for i in range(step_n):
            self._emit(AHDL_SEQ(ior, i, step_n), self.sched_time + i)

    def _make_port_init(self, new, target, node):
        assert new.func_scope.is_port()
        port = target.symbol().typ
        assert port.is_port()
        # make port signal
        self._port_sig(target.qualified_symbol())

    def _is_module_method(self, ir):
        return ir.is_a(CALL) and ir.func_scope.is_method() and ir.func_scope.parent.is_module()
