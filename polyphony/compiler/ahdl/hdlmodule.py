from collections import defaultdict
from copy import deepcopy
from typing import Any
from .ahdl import *
from .stg import STG
from ..common.env import env
from .hdlscope import HDLScope
from logging import getLogger
from .transformers.ahdlcloner import AHDLCloner
logger = getLogger(__name__)


class FSM(object):
    def __init__(self, name, scope, state_var):
        self.name = name
        self.scope = scope
        self.state_var:Signal = state_var
        self.stgs:list[STG] = []
        self.outputs:set[Signal] = set()
        self.reset_stms:list[AHDL_STM] = []

    def remove_stg(self, stg):
        self.stgs.remove(stg)
        if stg.is_main():
            for s in self.stgs:
                if s.parent is stg:
                    s.parent = None
    def clone(self):
        new = FSM(self.name, self.scope, self.state_var)
        new.stgs = [stg.clone() for stg in self.stgs]  # type: ignore[attr-defined]
        new.outputs = self.outputs.copy()
        new.reset_stms = self.reset_stms[:]
        return new

class HDLModule(HDLScope):
    def __init__(self, scope, name, qualified_name):
        super().__init__(scope, name, qualified_name)
        self._inputs:list[AHDL_VAR] = []
        self._outputs:list[AHDL_VAR] = []
        self.tasks = []
        self.parameters: dict[Signal, Any] = {}
        self.constants: dict[Signal, Any] = {}
        self.sub_modules = {}
        self.protocol_ports: list[tuple[Signal, AHDL_VAR, Signal]] = []
        self.functions = []
        self.decls: list[AHDL_DECL] = []
        self._decls_set: set[AHDL_DECL] = set()
        self.fsms = {}
        self.edge_detectors:set[tuple[AHDL_VAR, AHDL_EXP, AHDL_EXP]] = set()
        self.ahdl2dfgnode = {}
        self.clock_signal = None
        self.sleep_sentinel_signal = None

    @classmethod
    def is_hdlmodule_scope(cls, scope):
        return ((scope.is_module() and scope.is_instantiated())
                or scope.is_function_module()
                or scope.is_testbench())

    def __str__(self):
        s = '=' * 60 + '\n'
        s += f'HDLModule: {self.name}\n'
        s += '=' * 60 + '\n'

        # Signals section
        s += self.str_signals()
        s += '\n'

        # I/O ports section
        s += self.str_ios()
        s += '\n'

        # Parameters section
        if self.parameters:
            s += '-- PARAMETERS --\n'
            for sig, value in self.parameters.items():
                s += f'  {sig.name} = {value}\n'
            s += '\n'

        # Constants section
        if self.constants:
            s += '-- CONSTANTS --\n'
            for sig, value in self.constants.items():
                s += f'  {sig.name} = {value}\n'
            s += '\n'

        # Sub modules section
        if self.sub_modules:
            s += '-- SUB MODULES --\n'
            for name, hdlmodule, connections, param_map in self.sub_modules.values():
                s += f'  Module: {name}\n'
                if connections:
                    s += '    Connections:\n'
                    for sig, acc in connections:
                        s += f'      .{sig.name}({acc.name})\n'
                if param_map:
                    s += '    Parameters:\n'
                    for param, value in param_map.items():
                        s += f'      {param} = {value}\n'
                s += '\n'

        # Declarations section
        if self.decls:
            s += '-- DECLARATIONS --\n'
            for decl in self.decls:
                s += f'  {decl}\n'
            s += '\n'

        # FSM section
        if self.fsms:
            s += '-- FINITE STATE MACHINES --\n'
            for name, fsm in self.fsms.items():
                s += f'  FSM: {name}\n'
                s += f'    State Variable: {fsm.state_var.name}\n'

                if fsm.reset_stms:
                    s += '    Reset Statements:\n'
                    for stm in fsm.reset_stms:
                        s += f'      {stm}\n'

                if fsm.outputs:
                    s += '    Outputs:\n'
                    for output in fsm.outputs:
                        s += f'      {output.name}\n'

                if fsm.stgs:
                    s += '    State Transition Graphs:\n'
                    for i, stg in enumerate(fsm.stgs):
                        s += f'      STG {i}: {len(stg.states)} states\n'
                        for state in stg.states:
                            state_str = str(state)
                            state_lines = state_str.split('\n')
                            for line in state_lines:
                                if line.strip():
                                    s += f'        {line}\n'
                                else:
                                    s += '\n'
                s += '\n'

        # Tasks section
        if self.tasks:
            s += '-- TASKS --\n'
            for task in self.tasks:
                s += f'  {task}\n'
            s += '\n'

        # Edge detectors section
        if self.edge_detectors:
            s += '-- EDGE DETECTORS --\n'
            for var, old, new in self.edge_detectors:
                s += f'  {var.name}: {old} -> {new}\n'
            s += '\n'

        # Resource summary
        num_regs, num_nets, num_states = self.resources()
        s += '-- RESOURCE SUMMARY --\n'
        s += f'  Registers: {num_regs} bits\n'
        s += f'  Nets: {num_nets} bits\n'
        s += f'  States: {num_states}\n'

        s += '=' * 60 + '\n'
        return s

    def str_ios(self):
        s = '-- I/O PORTS --\n'

        # Input ports
        inputs = self.inputs()
        if inputs:
            s += '  Inputs:\n'
            for var in inputs:
                s += f'    {var.name:<20} : {var.sig}\n'
        else:
            s += '  Inputs: None\n'

        # Output ports
        outputs = self.outputs()
        if outputs:
            s += '  Outputs:\n'
            for var in outputs:
                s += f'    {var.name:<20} : {var.sig}\n'
        else:
            s += '  Outputs: None\n'
        return s

    def clone(self):
        new = HDLModule(self.scope, self.name, self.qualified_name)
        new, sig_maps = super().clone_core(new)
        new._inputs = self._inputs[:]
        new._outputs = self._outputs[:]
        new.tasks = self.tasks[:]
        for sig, value in self.parameters.items():
            new.parameters[sig_maps[new.name][sig]] = value
        for sig, value in self.constants.items():
            new.constants[sig_maps[new.name][sig]] = value
        # We already clone subscopes in super().clone_core()
        for name, sub_module, connections, param_map in self.sub_modules.values():
            orig_module_sig = self.signal(name)
            assert orig_module_sig is not None
            new_module_sig = sig_maps[new.name][orig_module_sig]
            new_sub_hdlscope = new.subscopes[new_module_sig]
            new.sub_modules[name] = (name, new_sub_hdlscope, connections, param_map)
        new.protocol_ports = self.protocol_ports[:]
        new.functions = self.functions[:]
        new.decls = self.decls[:]
        new._decls_set = self._decls_set.copy()
        for fsm in self.fsms.values():
            new.fsms[fsm.name] = FSM(fsm.name, new.scope, sig_maps[new.name][fsm.state_var])
        new.edge_detectors = self.edge_detectors.copy()
        new.ahdl2dfgnode = self.ahdl2dfgnode.copy()
        if self.clock_signal:
            new.clock_signal = sig_maps[new.name][self.clock_signal]
        if self.sleep_sentinel_signal:
            new.sleep_sentinel_signal = sig_maps[new.name][self.sleep_sentinel_signal]
        AHDLCloner(sig_maps).process(new)
        return new

    def add_input(self, var:AHDL_VAR):
        self._inputs.append(var)

    def inputs(self) -> list[AHDL_VAR]:
        return self._inputs

    def add_output(self, var:AHDL_VAR):
        self._outputs.append(var)

    def outputs(self) -> list[AHDL_VAR]:
        return self._outputs

    def connectors(self, prefix):
        # Collect protocol port connector signals to skip from regular I/O
        protocol_connector_sigs = {connector_sig for _, _, connector_sig in self.protocol_ports}
        for var in self._inputs + self._outputs:
            if var.sig in protocol_connector_sigs:
                continue  # Will be yielded below with nested var path
            if self.scope.is_module():
                ifname = var.hdl_name
            else:
                ifname = var.name[len(self.scope.base_name) + 1:]
            connector_name = f'{prefix}_{ifname}'
            attr = {'connector'}
            if var.sig.is_input():
                attr.add('reg')
                attr.add('initializable')
            else:
                attr.add('net')
            if var.sig.is_ctrl():
                attr.add('ctrl')
            yield (var, connector_name, attr)
        # Yield flattened protocol module ports with nested var paths
        # so that parent-of-parent signal replacement can match 3-level references
        for proto_sig, sub_var, connector_sig in self.protocol_ports:
            nested_var = AHDL_VAR((proto_sig,) + sub_var.vars, sub_var.ctx)
            connector_name = f'{prefix}_{connector_sig.name}'
            attr = {'connector'}
            if connector_sig.is_input():
                attr.add('reg')
                attr.add('initializable')
            else:
                attr.add('net')
            yield (nested_var, connector_name, attr)

    def add_task(self, task):
        self.tasks.append(task)

    def add_constant(self, name, value):
        assert isinstance(name, str)
        sig = self.gen_sig(name, env.config.default_int_width, {'constant'})
        self.constants[sig] = value

    def add_static_assignment(self, assign, tag=''):
        assert isinstance(assign, AHDL_ASSIGN)
        self.add_decl(assign)

    def get_static_assignment(self) -> list[AHDL_ASSIGN]:
        assigns = [decl for decl in self.decls if isinstance(decl, AHDL_ASSIGN)]
        return assigns

    def add_decl(self, decl):
        assert isinstance(decl, AHDL_DECL)
        if decl in self._decls_set:
            return
        self.decls.append(decl)
        self._decls_set.add(decl)

    def remove_decl(self, decl):
        assert isinstance(decl, AHDL_DECL)
        self.decls.remove(decl)
        self._decls_set.discard(decl)

    def add_sub_module(self, name:str, hdlmodule, connections:list[tuple[AHDL_VAR, Signal]], param_map=None):
        assert isinstance(name, str)
        self.sub_modules[name] = (name, hdlmodule, connections, param_map)

    def add_function(self, func, tag=''):
        assert isinstance(func, AHDL_FUNCTION)
        self.functions.append(func)

    def add_fsm(self, fsm_name, scope):
        state_sig = self.gen_sig(fsm_name + '_state', -1, {'reg'})
        fsm = FSM(fsm_name, scope, state_sig)
        self.fsms[fsm_name] = fsm

    def add_fsm_stg(self, fsm_name, stgs):
        assert fsm_name in self.fsms
        self.fsms[fsm_name].stgs = stgs
        for stg in stgs:
            stg.fsm = self.fsms[fsm_name]

    def add_fsm_output(self, fsm_name, output_sig):
        assert fsm_name in self.fsms
        self.fsms[fsm_name].outputs.add(output_sig)

    def add_fsm_reset_stm(self, fsm_name, ahdl_stm):
        assert fsm_name in self.fsms
        self.fsms[fsm_name].reset_stms.append(ahdl_stm)

    def add_edge_detector(self, var:AHDL_VAR, old:AHDL_EXP, new:AHDL_EXP):
        self.edge_detectors.add((var, old, new))

    def resources(self):
        num_of_regs = 0
        num_of_nets = 0
        for sig in sorted(self.signals.values(), key=lambda sig: sig.name):
            if sig.is_input() or sig.is_output():
                continue
            if sig.is_reg():
                if sig.width > 0:
                    num_of_regs += sig.width
            elif sig.is_regarray():
                num_of_regs += sig.width[0] * sig.width[1]
            elif sig.is_net():
                if sig.width > 0:
                    num_of_nets += sig.width
            elif sig.is_netarray():
                num_of_nets += sig.width[0] * sig.width[1]
        num_of_states = 0
        for _, fsm in self.fsms.items():
            for stg in fsm.stgs:
                num_of_states += len(stg.states)
        return num_of_regs, num_of_nets, num_of_states

    def get_clock_signal(self):
        if self.clock_signal is None:
            self.clock_signal = self.gen_sig(f'{self.name}_clktime', 64)
        return self.clock_signal

    def get_sleep_sentinel_signal(self):
        if self.sleep_sentinel_signal is None:
            self.sleep_sentinel_signal = self.gen_sig(f'{self.name}_sleep_sentinel', 64, {'reg'})
        return self.sleep_sentinel_signal

