from collections import defaultdict
from .ahdl import *
from .stg import STG
from ..common.env import env
from .hdlscope import HDLScope
from logging import getLogger
logger = getLogger(__name__)


class FSM(object):
    def __init__(self, name, scope, state_var):
        self.name = name
        self.scope = scope
        self.state_var:Signal = state_var
        self.stgs:list[STG] = []
        self.outputs:set[Signal] = set()
        self.reset_stms:list[AHDL_STM] = []


class HDLModule(HDLScope):
    #Port = namedtuple('Port', ['name', 'width'])
    def __init__(self, scope, name, qualified_name):
        super().__init__(scope, name, qualified_name)
        self._inputs:list[AHDL_VAR] = []
        self._outputs:list[AHDL_VAR] = []
        self.tasks = []
        self.parameters = []
        self.constants = {}
        self.sub_modules = {}
        self.functions = []
        self.decls = defaultdict(list)
        self.fsms = {}
        self.node2if = {}
        self.edge_detectors:set[tuple[AHDL_VAR, AHDL_EXP, AHDL_EXP]] = set()
        self.ahdl2dfgnode = {}
        self.clock_signal = None

    @classmethod
    def is_hdlmodule_scope(cls, scope):
        return ((scope.is_module() and scope.is_instantiated())
                or scope.is_function_module()
                or scope.is_testbench())

    def __str__(self):
        s = '---------------------------------\n'
        s += 'HDLModule {}\n'.format(self.name)
        s += self.str_signals()
        s += '\n'
        s += self.str_ios()
        s += '\n'
        s += '-- sub modules --\n'
        for name, hdlmodule, connections, param_map in self.sub_modules.values():
            s += '{} \n'.format(name)
            for sig, acc in connections:
                s += '    connection : .{}({}) \n'.format(sig.name, acc.name)
        s += '-- declarations --\n'
        for tag, decls in self.decls.items():
            s += 'tag : {}\n'.format(tag)
            for decl in decls:
                s += '  {}\n'.format(decl)
        s += '\n'
        s += '-- fsm --\n'
        for name, fsm in self.fsms.items():
            s += '---------------------------------\n'
            s += f'{name}\n'
            s += '---------------------------------\n'
            s += 'reset:\n'
            for stm in fsm.reset_stms:
                s += f'{stm}\n'
            for stg in fsm.stgs:
                for state in stg.states:
                    s += str(state)
        s += '\n'
        return s

    def str_ios(self):
        s = '-- I/O ports --\n'
        for var in self.inputs():
            s += f'{var.name} {var.sig}\n'
        for var in self.outputs():
            s += f'{var.name} {var.sig}\n'
        return s

    def add_input(self, var:AHDL_VAR):
        self._inputs.append(var)

    def inputs(self) -> list[AHDL_VAR]:
        return self._inputs

    def add_output(self, var:AHDL_VAR):
        self._outputs.append(var)

    def outputs(self) -> list[AHDL_VAR]:
        return self._outputs

    def connectors(self, prefix):
        for var in self._inputs + self._outputs:
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

    def add_task(self, task):
        self.tasks.append(task)

    def add_constant(self, name, value):
        assert isinstance(name, str)
        sig = self.gen_sig(name, env.config.default_int_width, {'constant'})
        self.constants[sig] = value

    def add_static_assignment(self, assign, tag=''):
        assert isinstance(assign, AHDL_ASSIGN)
        self.add_decl(tag, assign)

    def get_static_assignment(self):
        assigns = []
        for tag, decls in self.decls.items():
            assigns.extend([(tag, decl) for decl in decls if isinstance(decl, AHDL_ASSIGN)])
        return assigns

    def add_decl(self, tag, decl):
        assert isinstance(decl, AHDL_DECL)
        if isinstance(decl, AHDL_VAR_DECL):
            if decl.name in (d.name for d in self.decls[tag] if type(d) == type(decl)):
                return
        self.decls[tag].append(decl)

    def remove_decl(self, tag, decl):
        assert isinstance(decl, AHDL_DECL)
        self.decls[tag].remove(decl)

    def remove_signal_decl(self, sig):
        for tag, decls in self.decls.items():
            for decl in decls[:]:
                if isinstance(decl, AHDL_ASSIGN):
                    if decl.dst.is_a(AHDL_VAR) and decl.dst.sig is sig:
                        self.remove_decl(tag, decl)
                    elif decl.dst.is_a(AHDL_SUBSCRIPT) and decl.dst.memvar.sig is sig:
                        self.remove_decl(tag, decl)

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
                num_of_regs += sig.width
            elif sig.is_regarray():
                num_of_regs += sig.width[0] * sig.width[1]
            elif sig.is_net():
                num_of_nets += sig.width
            elif sig.is_netarray():
                num_of_nets += sig.width[0] * sig.width[1]
        num_of_states = 0
        for _, fsm in self.fsms.items():
            for stg in fsm.stgs:
                num_of_states += len(stg.states)
        return num_of_regs, num_of_nets, num_of_states

    def use_clock_time(self):
        if self.clock_signal is None:
            self.clock_signal = self.gen_sig(f'{self.name}_clktime', 64)
