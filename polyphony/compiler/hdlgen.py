from collections import OrderedDict, defaultdict, deque
from .common import get_src_text, INT_WIDTH
from .env import env
from .stg import STG, State
from .symbol import function_name, Symbol
from .ir import Ctx, CONST, ARRAY, MOVE
from .ahdl import *
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

    def _add_state_constants(self, scope):
        i = 0
        for stg in scope.stgs:
            for state in stg.states():
                self.module_info.add_constant(state.name, i)
                i += 1

    def _add_input_ports(self, module_name, scope):
        if scope.is_method():
            params = scope.params[1:]
        else:
            params = scope.params
        for i, (sym, _, _) in enumerate(params):
            if Type.is_list(sym.typ):
                continue

            hdl_name = '{}_IN{}'.format(module_name, i)
            orig_name = sym.hdl_name()
            if orig_name in scope.signals:
                in_sig = scope.rename_sig(orig_name, hdl_name)
            else:
                in_sig = scope.gen_sig(hdl_name, INT_WIDTH, ['in', 'wire'])
            self.module_info.add_data_input(in_sig)

    def _add_output_ports(self, module_name, scope, outputs):
        if Type.is_scalar(scope.return_type):
            out_sig = list(outputs)[0]
            outputs = filter(lambda tt: tt is not out_sig, set(outputs))
            for o in outputs:
                self.module_info.add_internal_reg(o)
            out_name = '{}_OUT0'.format(module_name)
            out_sig = scope.rename_sig(out_sig.name, out_name)
            out_sig.add_attribute('reg')
            self.module_info.add_data_output(out_sig)
        elif Type.is_seq(scope.return_type):
            raise NotImplementedError('return of a suquence type is not implemented')

    def _add_control_ports(self, module_name, scope):
        ready  = scope.gen_sig('{}_READY'.format(module_name), 1, ['wire'])
        accept = scope.gen_sig('{}_ACCEPT'.format(module_name), 1, ['wire'])
        valid  = scope.gen_sig('{}_VALID'.format(module_name), 1, ['reg'])
        self.module_info.add_ctrl_input(ready)
        self.module_info.add_ctrl_input(accept)
        self.module_info.add_ctrl_output(valid)

    def _add_internal_ports(self, module_name, locals):
        for sig in locals:
            sig = self.scope.gen_sig(sig.name, sig.width, sig.attributes)
            if sig.is_field():
                #renama field symbol in a method
                #sig.name = sig.name + '_' + module_name
                #self.module_info.add_internal_reg(sig)
                pass
            elif sig.is_condition():
                self.module_info.add_internal_wire(sig)
            #elif t.typ is None:
            #    pass
            elif sig.is_memif():
                pass
            elif sig.is_ctrl():
                pass
            else:
                assert (sig.is_wire() and not sig.is_reg()) or (not sig.is_wire() and sig.is_reg()) or (not sig.is_wire() and not sig.is_reg())
                if sig.is_wire():
                    self.module_info.add_internal_wire(sig)
                else:
                    self.module_info.add_internal_reg(sig)

    def _add_state_register(self, module_name, scope):
        #main_stg = scope.get_main_stg()
        states_n = 0
        for stg in scope.stgs:
            states_n += len(stg.states())
        #FIXME

        state_var = self.scope.gen_sig(module_name+'_state', states_n.bit_length(), ['statevar'])
        self.module_info.add_fsm_state_var(scope.name, state_var)
        self.module_info.add_internal_reg(state_var)

    def _add_submodule_func_instance(self, scope, inst_scope_name, inst_name, info, callee_scope):
        port_map = OrderedDict()
        logger.debug(info)

        #input ports
        for sig in info.data_inputs.values():
            num = sig.name.split('_IN')[1]
            param_name = inst_name + '_IN' + str(num)
            param_sig = self.scope.gen_sig(param_name, sig.width)
            port_map[sig.name] = param_sig
            self.module_info.add_internal_reg(param_sig)

        #output ports
        for sig in info.data_outputs.values():
            num = sig.name.split('_OUT')[1]
            param_name = inst_name + '_OUT' + str(num)
            param_sig = self.scope.gen_sig(param_name, sig.width)
            port_map[sig.name] = param_sig
            self.module_info.add_internal_wire(param_sig)

        #control ports
        ready_signal = self.scope.gen_sig(inst_name + '_READY', 1)
        accept_signal = self.scope.gen_sig(inst_name + '_ACCEPT', 1)
        valid_signal = self.scope.gen_sig(inst_name + '_VALID', 1)
        port_map[inst_scope_name + '_READY'] = ready_signal
        port_map[inst_scope_name + '_ACCEPT'] = accept_signal
        port_map[inst_scope_name + '_VALID'] = valid_signal
        self.module_info.add_internal_reg(ready_signal)
        self.module_info.add_internal_reg(accept_signal)
        self.module_info.add_internal_wire(valid_signal)

        #memory ports
        param_memnodes = [Type.extra(p.typ) for p, _, _ in callee_scope.params if Type.is_list(p.typ)]
        for node in param_memnodes:
            HDLMemPortMaker.make_port_map(scope, self.module_info, inst_name, node, node.preds, port_map)
        self.module_info.add_sub_module(inst_name, info, port_map)

    def _add_submodule_class_instance(self, scope, inst_scope_name, inst_name, info, callee_scope):
        port_map = OrderedDict()
        logger.debug(info)

        # I/O port for class fields
        for sym in callee_scope.symbols.values():
            if Type.is_scalar(sym.typ):
                submodule_field_name = 'field_{}'.format(sym.hdl_name())

                local_wire_name = '{}_{}'.format(inst_name, sym.hdl_name())
                ofield = submodule_field_name
                ofield_wire = self.scope.gen_sig(local_wire_name, INT_WIDTH) #TODO
                self.module_info.add_internal_wire(ofield_wire)
                port_map[ofield] = ofield_wire

                ifield = '{}_IN'.format(submodule_field_name)
                ifield_wire = self.scope.gen_sig('{}_IN'.format(local_wire_name), INT_WIDTH) #TODO
                self.module_info.add_internal_reg(ifield_wire)
                port_map[ifield] = ifield_wire

                ifield_ready = '{}_READY'.format(submodule_field_name)
                ifield_ready_wire = self.scope.gen_sig('{}_READY'.format(local_wire_name), 1)
                self.module_info.add_internal_reg(ifield_ready_wire)
                port_map[ifield_ready] = ifield_ready_wire
            elif Type.is_list(sym.typ):
                raise RuntimeError('list type field is not supported yet')

        #input ports
        for sig in info.data_inputs.values():
            if sig.is_field():
                pass
            else:
                method, num = sig.name.split('_IN')
                param_name = inst_name + '_' + method + '_IN' + str(num)
                param_sig = self.scope.gen_sig(param_name, sig.width)
                port_map[sig.name] = param_sig
                self.module_info.add_internal_reg(param_sig)

        #output ports
        for sig in info.data_outputs.values():
            if sig.is_field():
                pass
            else:
                method, num = sig.name.split('_OUT')
                param_name = inst_name + '_' + method + '_OUT' + str(num)
                param_sig = self.scope.gen_sig(param_name, sig.width)
                port_map[sig.name] = param_sig
                self.module_info.add_internal_wire(param_sig)

        # I/O port for class methods
        for child in callee_scope.children:
            assert child.is_method()

            port_name = child.orig_name

            #control ports
            ready_signal  = self.scope.gen_sig(inst_name + '_' + port_name + '_READY', 1)
            accept_signal = self.scope.gen_sig(inst_name + '_' + port_name + '_ACCEPT', 1)
            valid_signal  = self.scope.gen_sig(inst_name + '_' + port_name + '_VALID', 1)
            port_map[port_name + '_READY'] = ready_signal
            port_map[port_name +'_ACCEPT'] = accept_signal
            port_map[port_name +'_VALID'] = valid_signal
            self.module_info.add_internal_reg(ready_signal)
            self.module_info.add_internal_reg(accept_signal)
            self.module_info.add_internal_wire(valid_signal)

        #memory ports
        # TODO
        #for child in callee_scope.children:
        #    param_memnodes = [Type.extra(p.typ) for p, _, _ in child.params if Type.is_list(p.typ)]
        #    for node in param_memnodes:
        #        HDLMemPortMaker.make_port_map(scope, self.module_info, inst_name, node, node.preds, port_map)

        self.module_info.add_sub_module(inst_name, info, port_map)


    def _add_submodules(self, scope):
        for callee_scope, inst_names in scope.calls.items():
            inst_scope_name = callee_scope.orig_name
            # TODO: add primitive function hook here
            if inst_scope_name == 'print':
                continue
            info = callee_scope.module_info
            if callee_scope.is_class():
                add_func = self._add_submodule_class_instance
            else:
                add_func = self._add_submodule_func_instance
            for inst_name in inst_names:
                add_func(scope, inst_scope_name, inst_name, info, callee_scope)

    def _add_roms(self, scope):
        roms = deque()
        roms.extend(self.mrg.collect_readonly(scope))
        while roms:
            memnode = roms.pop()
            hdl_name = memnode.sym.hdl_name()
            output_sig = scope.gen_sig(hdl_name, INT_WIDTH) #TODO
            fname = AHDL_VAR(output_sig, Ctx.STORE)
            input_sig = scope.gen_sig(hdl_name+'_IN', INT_WIDTH) #TODO
            input = AHDL_VAR(input_sig, Ctx.LOAD)

            root = self.mrg.get_single_root(memnode)
            if root:
                array = root.initstm.src
                array_bits = len(array.items).bit_length()
                case_items = []
                for i, item in enumerate(array.items):
                    assert item.is_a(CONST)
                    connect = AHDL_CONNECT(fname, AHDL_CONST(item.value))
                    case_items.append(AHDL_CASE_ITEM(i, connect))
                case = AHDL_CASE(input, case_items)
            else:
                case_items = []
                for i, pred in enumerate(sorted(memnode.preds)):
                    if pred.scope is not scope:
                        roms.append(pred)
                    rom_func_name = pred.sym.hdl_name()
                    call = AHDL_FUNCALL(rom_func_name, [input])
                    connect = AHDL_CONNECT(fname, call)
                    case_val = '{}_bridge_sel[{}]'.format(hdl_name, i)
                    case_items.append(AHDL_CASE_ITEM(case_val, connect))
                rom_sel_sig = scope.gen_sig(hdl_name+'_bridge_sel', len(memnode.preds))
                case = AHDL_CASE(AHDL_CONST('1\'b1'), case_items)
                self.module_info.add_internal_reg(rom_sel_sig)
            rom_func = AHDL_FUNCTION(fname, [input], [case])
            self.module_info.add_function(rom_func)

    def process_func(self, scope):
        self.scope = scope
        self.mrg = env.memref_graph
        self.module_info = HDLModuleInfo(scope.orig_name, scope.name)
        self.static_assigns = []

        if not scope.is_testbench():
            self._add_state_constants(scope)

        outputs = set()
        locals = set()
        for stg in scope.stgs:
            self._preprocess_fsm(Phase1Preprocessor(self.module_info, scope, locals, outputs, None), stg)

        module_name = scope.stgs[0].name
        self._add_input_ports(module_name, scope)
        self._add_output_ports(module_name, scope, outputs)
        if not scope.is_testbench():
            self._add_control_ports(module_name, scope)
            self._add_state_register(module_name, scope)
        self._add_internal_ports(module_name, locals)

        for memnode in self.mrg.collect_writable(scope):
            self.memportmakers.append(HDLMemPortMaker.create(memnode, scope, self.module_info))

        self._add_submodules(scope)

        for memport in self.memportmakers:
            memport.make_hdl()

        self._add_roms(scope)

        self.module_info.add_fsm_stg(self.scope.name, self.scope.stgs)

        return self.module_info

    def process_class(self, scope):
        assert scope.is_class()
        self.scope = scope
        self.mrg = env.memref_graph
        self.module_info = HDLModuleInfo(scope.orig_name, scope.name)
        self.static_assigns = []

        for s in scope.children:
            self._add_state_constants(s)

        field_accesses = defaultdict(list)
        for s in scope.children:
            outputs = set()
            locals = set()
            for stg in s.stgs:
                self._preprocess_fsm(Phase1Preprocessor(self.module_info, s, locals, outputs, field_accesses), stg)
            self._add_input_ports(s.orig_name, s)
            self._add_output_ports(s.orig_name, s, outputs)
            self._add_control_ports(s.orig_name, s)
            self._add_internal_ports(s.orig_name, locals)
            self._add_state_register(s.orig_name, s)
            self._add_submodules(s)
            self._add_roms(s)

        # I/O port for class fields
        for sym in self.scope.symbols.values():
            if Type.is_scalar(sym.typ): # skip a method
                field = 'field_{}'.format(sym.hdl_name())
                field_in = scope.gen_sig(field + '_IN', INT_WIDTH, ['in', 'wire', 'field'])
                field_ready = scope.gen_sig(field + '_READY', 1, ['in', 'wire', 'field', 'ctrl'])
                field    = scope.gen_sig(field, INT_WIDTH, ['out', 'reg', 'field'])
                self.module_info.add_data_input(field_in)
                self.module_info.add_data_output(field)
                self.module_info.add_ctrl_input(field_ready)
                self.module_info.add_class_field(field)
                #self.module_info.add_sync_assignment(AHDL_MOVE(AHDL_VAR(field_out_sym, Ctx.STORE), AHDL_VAR(field_in_sym, Ctx.LOAD)))
            elif Type.is_list(sym.typ):
                raise RuntimeError('list type field is not supported yet')

        for name, sub_module_info, port_map, param_map in self.module_info.sub_modules.values():
            #pass#assert False
            for din in sub_module_info.data_inputs:
                sig = scope.gen_sig('{}_field_{}'.format(name, din.name), INT_WIDTH, ['in', 'wire', 'field'])

            for sym in sym_scope.symbols.values():
                if Type.is_scalar(sym.typ): # skip a method
                    field = sym.name
                    field_in = scope.gen_sig(field + '_IN', INT_WIDTH, ['in', 'wire', 'field'])
                    field_ready = scope.gen_sig(field + '_READY', 1, ['in', 'wire', 'field', 'ctrl'])
                    field    = scope.gen_sig(field, INT_WIDTH, ['out', 'reg', 'field'])
                    self.module_info.add_data_input(field_in)
                    self.module_info.add_data_output(field)
                    self.module_info.add_ctrl_input(field_ready)
                    self.module_info.add_class_field(field)
                    

        for field_name, accesses in field_accesses.items():
            conds = []
            codes_list = []
            for method_scope, state, ahdl in accesses:
                state_var = self.module_info.fsms[method_scope.name].state_var
                cond = AHDL_OP('Eq', AHDL_VAR(state_var, Ctx.LOAD), AHDL_SYMBOL(state.name))
                conds.append(cond)
                codes_list.append([ahdl])
            #
            field       = scope.signals[field_name]
            field_in    = scope.signals[field_name + '_IN']
            field_ready = scope.signals[field_name + '_READY']
            cond = AHDL_OP('Eq', AHDL_VAR(field_ready, Ctx.LOAD), AHDL_CONST(1))
            conds.append(cond)
            mv = AHDL_MOVE(AHDL_VAR(field, Ctx.STORE), AHDL_VAR(field_in, Ctx.LOAD))
            codes_list.append([mv])
            #
            conds.append(AHDL_CONST(1))
            mv = AHDL_MOVE(AHDL_VAR(field, Ctx.STORE), AHDL_VAR(field, Ctx.LOAD))
            codes_list.append([mv])

            ifexp = AHDL_IF(conds, codes_list)
            self.module_info.add_field_access(field, ifexp)

        for memnode in self.mrg.collect_writable(self.scope):
            self.memportmakers.append(HDLMemPortMaker.create(memnode, scope, self.module_info))

        for memport in self.memportmakers:
            memport.make_hdl()

        #FIXME
        if self.scope.stgs:
            self.module_info.add_fsm_stg(self.scope.name, self.scope.stgs)
        for s in scope.children:
            self.module_info.add_fsm_stg(s.name, s.stgs)

        return self.module_info

    def _preprocess_fsm(self, preprocessor, stg):
        assert stg
        for state in stg.states():
            preprocessor.current_state = state
            remove_codes = []
            for code in state.codes:
                preprocessor.visit(code)
                if getattr(code, 'removed', None):
                    remove_codes.append(code)
            for code in remove_codes:
                state.codes.remove(code)

            #visit the code in next_states info
            for condition, _, codes in state.next_states:
                if condition:
                    preprocessor.visit(condition)
                if codes:
                    for code in codes:
                        preprocessor.visit(code)
                

class Phase1Preprocessor:
    ''' this class corrects inputs and outputs and locals'''
    def __init__(self, module_info, scope, local_temps, output_temps, field_accesses):
        self.module_info = module_info
        self.scope = scope
        self.local_temps = local_temps
        self.output_temps = output_temps
        self.field_accesses = field_accesses
        self.module_constants = [c for c, _ in self.module_info.constants]
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

    def visit_AHDL_OP(self, ahdl):
        self.visit(ahdl.left)
        if ahdl.right:
            self.visit(ahdl.right)

    def visit_AHDL_NOP(self, ahdl):
        pass

    def visit_AHDL_MOVE(self, ahdl):
        self.visit(ahdl.src)
        self.visit(ahdl.dst)
        if self.scope.is_method():
            if ahdl.dst.sig.is_field():
                assert self.field_accesses is not None
                self.field_accesses[ahdl.dst.sig.name].append((self.scope, self.current_state, ahdl))
                ahdl.removed = True
            else:
                self.module_info.add_fsm_output(self.scope.name, ahdl.dst.sig)

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

