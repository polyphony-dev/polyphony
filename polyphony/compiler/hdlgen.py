from collections import OrderedDict, defaultdict, deque
from .common import get_src_text
from .env import env
from .stg import STG, State
from .symbol import Symbol
from .ir import Ctx, CONST, ARRAY, MOVE
from .ahdl import *
#from collections import namedtuple
from .hdlmoduleinfo import HDLModuleInfo
from .hdlmemport import HDLMemPortMaker, HDLRegArrayPortMaker
from .type import Type
from .hdlinterface import *
from .memref import *
from .utils import replace_item
from logging import getLogger, DEBUG
logger = getLogger(__name__)
import pdb


class HDLGenPreprocessor:
    """ 
    HDLGenPreprocessor does following tasks
      - detect input/output port name
      - detect internal port name
      - rename input/output variable name to 'IN*' or 'OUT*'
      - collect each State's name (to define as a constant params in the hdl source)
    """
    def __init__(self):
        pass

    def _add_state_constants(self, scope):
        i = 0
        for stg in scope.stgs:
            for state in stg.states:
                self.module_info.add_state_constant(state.name, i)
                i += 1

    def _add_input_ports(self, funcif, scope):
        if scope.is_method():
            params = scope.params[1:]
        else:
            params = scope.params
        for i, (sym, _, _) in enumerate(params):
            if Type.is_int(sym.typ):
                funcif.add_data_in(sym.hdl_name(), Type.width(sym.typ))
            elif Type.is_list(sym.typ):
                continue
 
    def _add_output_ports(self, funcif, scope):
        if Type.is_scalar(scope.return_type):
            funcif.add_data_out('out_0', Type.width(scope.return_type))
        elif Type.is_seq(scope.return_type):
            raise NotImplementedError('return of a suquence type is not implemented')

    def _add_internal_ports(self, module_name, locals):
        for sig in locals:
            sig = self.scope.gen_sig(sig.name, sig.width, sig.attributes)
            if sig.is_field():
                pass
            elif sig.is_condition():
                self.module_info.add_internal_net(sig)
            elif sig.is_memif():
                pass
            elif sig.is_ctrl():
                pass
            else:
                assert (sig.is_net() and not sig.is_reg()) or (not sig.is_net() and sig.is_reg()) or (not sig.is_net() and not sig.is_reg())
                if sig.is_net():
                    self.module_info.add_internal_net(sig)
                else:
                    self.module_info.add_internal_reg(sig)

    def _add_state_register(self, module_name, scope):
        #main_stg = scope.get_main_stg()
        states_n = 0
        for stg in scope.stgs:
            states_n += len(stg.states)
        #FIXME

        state_var = self.scope.gen_sig(module_name+'_state', states_n.bit_length(), ['statevar'])
        self.module_info.add_fsm_state_var(scope.name, state_var)
        self.module_info.add_internal_reg(state_var)


    def _add_submodules(self, scope):
        
        for callee_scope, inst_names in scope.callee_instances.items():
            inst_scope_name = callee_scope.orig_name
            # TODO: add primitive function hook here
            if inst_scope_name == 'print':
                continue
            info = callee_scope.module_info
            accessors = info.interfaces[:]
            for inst_name in inst_names:
                self.module_info.add_sub_module(inst_name, info, accessors)
    def _add_roms(self, scope):
        roms = deque()

        roms.extend(self.mrg.collect_readonly_sink(scope))
        while roms:
            memnode = roms.pop()
            hdl_name = memnode.sym.hdl_name()
            source = memnode.single_source()
            if source:
                source_scope = list(source.scopes)[0]
                if source_scope.is_class(): # class field rom
                    hdl_name = source_scope.orig_name + '_field_' + hdl_name
            output_sig = scope.gen_sig(hdl_name, memnode.width) #TODO
            fname = AHDL_VAR(output_sig, Ctx.STORE)
            input_sig = scope.gen_sig(hdl_name+'_in', memnode.width) #TODO
            input = AHDL_VAR(input_sig, Ctx.LOAD)

            if source:
                array = source.initstm.src
                case_items = []
                for i, item in enumerate(array.items):
                    assert item.is_a(CONST)
                    connect = AHDL_CONNECT(fname, AHDL_CONST(item.value))
                    case_items.append(AHDL_CASE_ITEM(i, connect))
                case = AHDL_CASE(input, case_items)
            else:
                case_items = []
                n2o = memnode.pred_branch()
                for i, pred in enumerate(n2o.orig_preds):
                    assert pred.is_sink()
                    if scope not in pred.scopes:
                        roms.append(pred)
                    rom_func_name = pred.sym.hdl_name()
                    call = AHDL_FUNCALL(rom_func_name, [input])
                    connect = AHDL_CONNECT(fname, call)
                    case_val = '{}_cs[{}]'.format(hdl_name, i)
                    case_items.append(AHDL_CASE_ITEM(case_val, connect))
                rom_sel_sig = scope.gen_sig(hdl_name+'_cs', len(memnode.pred_ref_nodes()))
                case = AHDL_CASE(AHDL_SYMBOL('1\'b1'), case_items)
                self.module_info.add_internal_reg(rom_sel_sig)
            rom_func = AHDL_FUNCTION(fname, [input], [case])
            self.module_info.add_function(rom_func)

    def process_func(self, scope):
        self.scope = scope
        self.mrg = env.memref_graph
        self.module_info = HDLModuleInfo(scope, scope.orig_name, scope.name)
        self.static_assigns = []

        if not scope.is_testbench():
            self._add_state_constants(scope)

        outputs = set()
        locals = set()
        field_accesses = defaultdict(list)
        for stg in scope.stgs:
            self._preprocess_fsm(Phase1Preprocessor(self.module_info, scope, locals, outputs, field_accesses), stg)

        module_name = scope.stgs[0].name
        if not scope.is_testbench():
            self._add_state_register(module_name, scope)
            funcif = FunctionInterface('')
            self._add_input_ports(funcif, scope)
            self._add_output_ports(funcif, scope)
            self.module_info.add_interface(funcif)

        self._add_internal_ports(module_name, locals)

        for memnode in self.mrg.collect_ram(scope):
            HDLMemPortMaker(memnode, scope, self.module_info).make_port()

        for memnode in self.mrg.collect_immutable(scope):
            if not memnode.is_writable():
                continue
            HDLRegArrayPortMaker(memnode, scope, self.module_info).make_port()

        self._add_submodules(scope)

        for field_name, accesses in field_accesses.items():
            self.module_info.add_internal_field_access(field_name, accesses)

        self._add_roms(scope)

        self.module_info.add_fsm_stg(self.scope.name, self.scope.stgs)

        self._rename_signal(self.scope)
        return self.module_info

    def _rename_signal(self, scope):
        for input_sig in [sig for sig in scope.signals.values() if sig.is_input()]:
            if scope.is_method():
                new_name = '{}_{}_{}'.format(scope.parent.orig_name, scope.orig_name, input_sig.name)
            else:
                new_name = '{}_{}'.format(scope.orig_name, input_sig.name)
            scope.rename_sig(input_sig.name,  new_name)
        for output_sig in [sig for sig in scope.signals.values() if sig.is_output()]:
            # TODO
            if scope.is_method():
                out_name = '{}_{}_out_0'.format(scope.parent.orig_name, scope.orig_name)
            else:
                out_name = '{}_out_0'.format(scope.orig_name)
            scope.rename_sig(output_sig.name, out_name)
 
    def process_class(self, scope):
        assert scope.is_class()
        self.scope = scope
        self.mrg = env.memref_graph
        self.module_info = HDLModuleInfo(scope, scope.orig_name, scope.name)
        self.static_assigns = []

        for s in scope.children:
            self._add_state_constants(s)

        field_accesses = defaultdict(list)
        for s in scope.children:
            outputs = set()
            locals = set()
            for stg in s.stgs:
                self._preprocess_fsm(Phase1Preprocessor(self.module_info, s, locals, outputs, field_accesses), stg)
            funcif = FunctionInterface(s.orig_name, is_method=True)
            self._add_input_ports(funcif, s)
            self._add_output_ports(funcif, s)
            self.module_info.add_interface(funcif)
            for p in funcif.outports():
                pname = funcif.port_name(self.module_info.name, p)
                self.module_info.add_fsm_output(s.name, s.gen_sig(pname, p.width, ['reg']))
            self._add_internal_ports(s.orig_name, locals)
            self._add_state_register(s.orig_name, s)
            self._add_submodules(s)
            for memnode in self.mrg.collect_ram(s):
                memportmaker = HDLMemPortMaker(memnode, s, self.module_info).make_port()

            self._add_roms(s)
        # I/O port for class fields
        
        for sym in self.scope.symbols.values():
            if Type.is_scalar(sym.typ): # skip a method
                fieldif = RegFieldInterface(sym.hdl_name(), Type.width(sym.typ))
                self.module_info.add_interface(fieldif)
            elif Type.is_list(sym.typ):
                memnode = Type.extra(sym.typ)
                fieldif = RAMFieldInterface(memnode.name(), memnode.width, memnode.addr_width(), True)
                self.module_info.add_interface(fieldif)
            elif Type.is_object(sym.typ):
                # add interface at add_submodule()
                pass

        for field_name, accesses in field_accesses.items():
            self.module_info.add_internal_field_access(field_name, accesses)

        

        #FIXME
        if self.scope.stgs:
            self.module_info.add_fsm_stg(self.scope.name, self.scope.stgs)
        for s in scope.children:
            self.module_info.add_fsm_stg(s.name, s.stgs)
            self._rename_signal(s)

        return self.module_info

    def _preprocess_fsm(self, preprocessor, stg):
        assert stg
        for state in stg.states:
            preprocessor.current_state = state
            remove_codes = []
            for code in state.codes:
                preprocessor.visit(code)
                if getattr(code, 'removed', None):
                    remove_codes.append((code, AHDL_NOP(code)))
            for code, nop in remove_codes:
                replace_item(state.codes, code, nop)
                

class Phase1Preprocessor:
    ''' this class corrects inputs and outputs and locals'''
    def __init__(self, module_info, scope, local_temps, output_temps, field_accesses):
        self.module_info = module_info
        self.scope = scope
        self.local_temps = local_temps
        self.output_temps = output_temps
        self.field_accesses = field_accesses
        self.module_constants = [c for c, _ in self.module_info.state_constants]
        self.current_state = None

    def visit_AHDL_CONST(self, ahdl):
        pass

    def visit_AHDL_VAR(self, ahdl):
        if ahdl.sig.is_ctrl() or ahdl.sig.is_input() or ahdl.sig.name in self.module_constants:
            pass
        elif ahdl.sig.is_output():
            self.output_temps.add(ahdl.sig)
        else:
            self.local_temps.add(ahdl.sig)
        #else:
        #    text = ahdl.sym.name #get_src_text(ir)
        #    raise RuntimeError('free variable is not supported yet.\n' + text)

    def visit_AHDL_MEMVAR(self, ahdl):
        pass

    def visit_AHDL_SUBSCRIPT(self, ahdl):
        pass

    def visit_AHDL_OP(self, ahdl):
        self.visit(ahdl.left)
        if ahdl.right:
            self.visit(ahdl.right)

    def visit_AHDL_NOP(self, ahdl):
        pass

    def visit_AHDL_MOVE(self, ahdl):
        self.visit(ahdl.src)
        self.visit(ahdl.dst)

    def visit_AHDL_STORE(self, ahdl):
        self.visit(ahdl.src)
        self.visit(ahdl.mem)
        self.visit(ahdl.offset)

    def visit_AHDL_LOAD(self, ahdl):
        self.visit(ahdl.mem)
        self.visit(ahdl.dst)
        self.visit(ahdl.offset)

    def visit_AHDL_FIELD_MOVE(self, ahdl):
        self.visit(ahdl.src)
        self.visit(ahdl.dst)

        assert self.field_accesses is not None
        field = '{}_field_{}'.format(ahdl.inst_name, ahdl.attr_name)
        self.field_accesses[field].append((self.scope, self.current_state, ahdl))
        ahdl.removed = True

    def visit_AHDL_FIELD_STORE(self, ahdl):
        self.visit(ahdl.src)

        assert self.field_accesses is not None
        self.field_accesses[ahdl.mem.sig.name].append((self.scope, self.current_state, ahdl))
        ahdl.removed = True

    def visit_AHDL_FIELD_LOAD(self, ahdl):
        self.visit(ahdl.dst)

        assert self.field_accesses is not None
        self.field_accesses[ahdl.mem.sig.name].append((self.scope, self.current_state, ahdl))
        ahdl.removed = True

    def visit_AHDL_POST_PROCESS(self, ahdl):
        if isinstance(ahdl.factor, AHDL_FIELD_MOVE):
            field = '{}_field_{}'.format(ahdl.factor.inst_name, ahdl.factor.attr_name)
            self.field_accesses[field].append((self.scope, self.current_state, ahdl))
            ahdl.removed = True
        elif isinstance(ahdl.factor, AHDL_FIELD_STORE):
            self.field_accesses[ahdl.factor.mem.sig.name].append((self.scope, self.current_state, ahdl))
            ahdl.removed = True
        elif isinstance(ahdl.factor, AHDL_FIELD_LOAD):
            self.field_accesses[ahdl.factor.mem.sig.name].append((self.scope, self.current_state, ahdl))
            ahdl.removed = True

    def visit_AHDL_IF(self, ahdl):
        for cond in ahdl.conds:
            if cond:
                self.visit(cond)
        for codes in ahdl.codes_list:
            for code in codes:
                self.visit(code)

    def visit_AHDL_MODULECALL(self, ahdl):
        for arg in ahdl.args:
            self.visit(arg)
        if ahdl.scope.is_class() or ahdl.scope.is_method():
            assert self.field_accesses is not None
            self.field_accesses[ahdl.prefix].append((self.scope, self.current_state, ahdl))
            ahdl.removed = True

    def visit_AHDL_FUNCALL(self, ahdl):
        for arg in ahdl.args:
            self.visit(arg)

    def visit_AHDL_PROCCALL(self, ahdl):
        for arg in ahdl.args:
            self.visit(arg)

    def visit_SET_READY(self, ahdl):
        modulecall = ahdl.args[0]
        if modulecall.scope.is_class() or modulecall.scope.is_method():
            assert self.field_accesses is not None
            self.field_accesses[modulecall.prefix].append((self.scope, self.current_state, ahdl))
            ahdl.removed = True

    def visit_ACCEPT_IF_VALID(self, ahdl):
        modulecall = ahdl.args[0]
        if modulecall.scope.is_class() or modulecall.scope.is_method():
            assert self.field_accesses is not None
            self.field_accesses[modulecall.prefix].append((self.scope, self.current_state, ahdl))
            ahdl.removed = True

    def visit_GET_RET_IF_VALID(self, ahdl):
        modulecall = ahdl.args[0]
        dst = ahdl.args[1]
        self.visit(dst)
        
    def visit_SET_ACCEPT(self, ahdl):
        modulecall = ahdl.args[0]
        if modulecall.scope.is_class() or modulecall.scope.is_method():
            assert self.field_accesses is not None
            self.field_accesses[modulecall.prefix].append((self.scope, self.current_state, ahdl))
            ahdl.removed = True

    def visit_AHDL_META(self, ahdl):
        method = 'visit_' + ahdl.metaid
        visitor = getattr(self, method, None)
        return visitor(ahdl)

    def visit_WAIT_INPUT_READY(self, ahdl):
        if ahdl.codes:
            for code in ahdl.codes:
                self.visit(code)

    def visit_WAIT_OUTPUT_ACCEPT(self, ahdl):
        pass

    def visit_WAIT_RET_AND_GATE(self, ahdl):
        pass

    def visit_AHDL_META_WAIT(self, ahdl):
        method = 'visit_' + ahdl.metaid
        visitor = getattr(self, method, None)
        return visitor(ahdl)

    def visit_AHDL_TRANSITION(self, ahdl):
        pass

    def visit_AHDL_TRANSITION_IF(self, ahdl):
        self.visit_AHDL_IF(ahdl)

    def visit(self, ahdl):
        method = 'visit_' + ahdl.__class__.__name__
        visitor = getattr(self, method, None)
        return visitor(ahdl)

