from collections import OrderedDict, defaultdict
from .common import get_src_text, INT_WIDTH
from .env import env
from .stg import STG, State
from .symbol import function_name
from .ir import CONST, ARRAY, MOVE
from .ahdl import AHDL_CONST, AHDL_VAR, AHDL_CONCAT, AHDL_OP, AHDL_IF_EXP, AHDL_ASSIGN, AHDL_CONNECT, AHDL_FUNCALL, AHDL_FUNCTION, AHDL_CASE, AHDL_CASE_ITEM, AHDL_MUX, AHDL_DEMUX
#from collections import namedtuple
from .hdlmoduleinfo import HDLModuleInfo
from .hdlmemport import HDLMemPortMaker
from .type import Type
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
        self.memportmakers = []

    def phase1(self, scope):
        self.scope = scope
        self.mrg = env.memref_graph
        self.module_info = HDLModuleInfo(scope.orig_name, scope.name)
        self.output_temps = []
        self.local_temps = set()
        self.static_assigns = []

        #state constants
        is_testbench = 'testbench' in self.scope.attributes
        if not is_testbench:
            i = 0
            for stg in self.scope.stgs:
                for state in stg.states():
                    self.module_info.add_constant(state.name, i)
                    i += 1

        for stg in self.scope.stgs:
            self._preprocess_fsm(Phase1Preprocessor(self), stg)

        mod_name = self.scope.stgs[0].name
        #input port
        for i, (sym, _, _) in enumerate(self.scope.params):
            if Type.is_list(sym.typ):
                continue
            in_name = '{}_IN{}'.format(mod_name, i)
            sym.name = in_name
            self.module_info.add_input(in_name, 'datain', INT_WIDTH)#TODO
        #output port
        if Type.is_scalar(self.scope.return_type):
            out = self.output_temps[-1]
            outputs = filter(lambda tt: tt is not out, set(self.output_temps))
            for o in outputs:
                self.module_info.add_internal_reg(o.hdl_name(), INT_WIDTH)
            out_name = '{}_OUT0'.format(mod_name)
            out.name = out_name
            out_width = INT_WIDTH
            self.module_info.add_output(out_name, 'dataout', out_width)
        elif Type.is_seq(self.scope.return_type):
            raise NotImplementedError('return of a suquence type is not implemented')

        main_stg = self.scope.get_main_stg()

        #internal port
        #FIXME: need more safe detection mechanism for special signals
        logger.debug('::::::::::::::::::::::::::::')
        for t in self.local_temps:
            logger.debug(t)
            if t.typ == '' or t.typ == 'in' or t.typ == 'out':
                continue
            elif t.is_condition():
                self.module_info.add_internal_wire(t.hdl_name(), 1)
            else:
                if t.typ == 'wire':
                    self.module_info.add_internal_wire(t.hdl_name(), INT_WIDTH)
                elif t.typ is None:
                    pass
                else:
                    self.module_info.add_internal_reg(t.hdl_name(), INT_WIDTH)
        # state register
        states_n = 0
        for stg in self.scope.stgs:
            states_n += len(stg.states())
        state_var = main_stg.state_var_sym.hdl_name()
        self.module_info.add_internal_reg(state_var, states_n.bit_length(), '')

     
        for memnode in self.mrg.collect_writable(self.scope):
            self.memportmakers.append(HDLMemPortMaker.create(memnode, self.scope, self.module_info))

        #add sub modules
        for callee_scope, inst_names in self.scope.calls.items():
            func_name = callee_scope.orig_name
            # TODO: add primitive function hook here
            if func_name == 'print':
                continue

            info = callee_scope.module_info

            for inst in inst_names:
                port_map = OrderedDict()
                logger.debug(info)
                #input ports
                for name, typ, width in info.inputs:
                    if '_IN' not in name or typ != 'datain':
                        continue
                    for i in range(len(info.inputs)):
                        if name.endswith('_IN' + str(i)):
                            param_name = inst + '_IN' + str(i)
                            port_map[name] = param_name
                            self.module_info.add_internal_reg(param_name, width)
                            break
                
                #output ports
                for name, typ, width in info.outputs:
                    if '_OUT' not in name or typ != 'dataout':
                        continue
                    for i in range(len(info.outputs)):
                        if name.endswith('_OUT' + str(i)):
                            param_name = inst + '_OUT' + str(i)
                            port_map[name] = param_name
                            self.module_info.add_internal_wire(param_name, width)
                            break

                #control ports
                ready_signal = inst + '_READY'
                accept_signal = inst + '_ACCEPT'
                valid_signal = inst + '_VALID'
                port_map[func_name + '_READY'] = ready_signal
                port_map[func_name + '_ACCEPT'] = accept_signal
                port_map[func_name + '_VALID'] = valid_signal
                self.module_info.add_internal_reg(ready_signal, 1)
                self.module_info.add_internal_reg(accept_signal, 1)
                self.module_info.add_internal_wire(valid_signal, 1)

                #memory ports
                param_memnodes = [Type.extra(p.typ) for p, _, _ in callee_scope.params if Type.is_list(p.typ)]
                for node in param_memnodes:
                    HDLMemPortMaker.make_port_map(self.scope, self.module_info, inst, node, node.preds, port_map)
                self.module_info.add_sub_module(inst, info, port_map)

        for memport in self.memportmakers:
            memport.make_hdl()


        # add rom as function
        for memnode in self.mrg.collect_readonly(self.scope):
            hdl_name = memnode.sym.hdl_name()
            output_sym = self.scope.gen_sym(hdl_name)
            output_sym.width = INT_WIDTH #TODO
            fname = AHDL_VAR(output_sym)
            input_sym = self.scope.gen_sym(hdl_name+'_IN')
            input_sym.width = INT_WIDTH #TODO
            input = AHDL_VAR(input_sym)

            if not memnode.is_joinable():
                root = self.mrg.get_single_root(memnode)
                array = root.initstm.src
                array_bits = len(array.items).bit_length()
                case_items = []
                for i, item in enumerate(array.items):
                    assert isinstance(item, CONST)
                    connect = AHDL_CONNECT(fname, AHDL_CONST(item.value))
                    case_items.append(AHDL_CASE_ITEM(i, connect))
                case = AHDL_CASE(input, case_items)
            else:
                case_items = []
                for i, pred in enumerate(sorted(memnode.preds)):
                    rom_func_name = pred.sym.hdl_name()
                    call = AHDL_FUNCALL(rom_func_name, [input])
                    connect = AHDL_CONNECT(fname, call)
                    case_items.append(AHDL_CASE_ITEM(i, connect))
                rom_sel_sym = self.scope.gen_sym(hdl_name+'_sel')
                rom_sel_sym.width = len(memnode.preds).bit_length()
                sel = AHDL_VAR(rom_sel_sym)
                case = AHDL_CASE(sel, case_items)
                self.module_info.add_internal_reg(rom_sel_sym.name, rom_sel_sym.width, '')
            rom_func = AHDL_FUNCTION(fname, [input], [case])
            self.module_info.add_function(rom_func)

        return self.module_info


    def _preprocess_fsm(self, preprocessor, stg):
        assert stg
        for state in stg.states():
            for code in state.codes:
                preprocessor.visit(code)
            #visit the code in next_states info
            for condition, _, codes in state.next_states:
                if condition:
                    preprocessor.visit(condition)
                if codes:
                    for code in codes:
                        preprocessor.visit(code)
                

class Phase1Preprocessor:
    ''' this class corrects inputs and outputs and locals'''
    def __init__(self, host):
        self.host = host

    def visit_AHDL_CONST(self, ahdl):
        pass

    def visit_AHDL_VAR(self, ahdl):
        if ahdl.sym.is_return():
            self.host.output_temps.append(ahdl.sym)
        elif Type.is_list(ahdl.sym.typ):
            pass
        elif self.host.scope.has_param(ahdl.sym):
            pass
        else:
            if ahdl.sym.name in [c for c, _ in self.host.module_info.constants]:
                pass
            elif ahdl.sym.name[0] == '!' or ahdl.sym.name[0] == '@' or self.host.scope.has_sym(ahdl.sym.name):
                self.host.local_temps.add(ahdl.sym)
            else:
                text = ahdl.sym.name #get_src_text(ir)
                raise RuntimeError('free variable is not supported yet.\n' + text)

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

    def visit_AHDL_LOAD(self, ahdl):
        self.visit(ahdl.mem)
        self.visit(ahdl.dst)

    def visit_AHDL_MEM(self, ahdl):
        self.visit(ahdl.offset)

    def visit_AHDL_IF(self, ahdl):
        for cond in ahdl.conds:
            if cond:
                self.visit(cond)
        for codes in ahdl.codes_list:
            for code in codes:
                self.visit(code)

    def visit_AHDL_FUNCALL(self, ahdl):
        for arg in ahdl.args:
            self.visit(arg)

    def visit_AHDL_PROCCALL(self, ahdl):
        for arg in ahdl.args:
            self.visit(arg)

    def visit_AHDL_META(self, ahdl):
        pass

    def visit(self, ahdl):
        method = 'visit_' + ahdl.__class__.__name__
        visitor = getattr(self, method, None)
        return visitor(ahdl)

