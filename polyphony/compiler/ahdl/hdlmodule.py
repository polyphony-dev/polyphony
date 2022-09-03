﻿from collections import defaultdict, OrderedDict
from .ahdl import *
from ..ir.symbol import Symbol
from ..common.env import env
from logging import getLogger
logger = getLogger(__name__)


class FSM(object):
    def __init__(self, name, scope):
        self.name = name
        self.scope = scope
        self.state_var = None
        self.stgs = []
        self.outputs = set()
        self.reset_stms = []


class HDLScope(object):
    def __init__(self, scope, name, qualified_name):
        self.scope = scope
        self.name = name
        self.qualified_name = qualified_name
        self.signals = {}
        self.sig2sym = {}
        self.sym2sigs = defaultdict(list)
        self.subscope = {}

    def __str__(self):
        s = '---------------------------------\n'
        s += 'HDLScope {}\n'.format(self.name)
        s += '  -- signals --\n'
        for sig in self.signals.values():
            s += f'{sig.name}[{sig.width}] {sig.tags}\n'
        s += '\n'
        return s

    def __repr__(self):
        return self.name

    def gen_sig(self, name, width, tag=None, sym=None):
        if name in self.signals:
            sig = self.signals[name]
            sig.width = width
            if tag:
                sig.add_tag(tag)
            return sig
        sig = Signal(name, width, tag, sym)
        self.signals[name] = sig
        if sym:
            self.sig2sym[sig] = sym
            self.sym2sigs[sym].append(sig)
        return sig

    def signal(self, key):
        if isinstance(key, str):
            if key in self.signals:
                return self.signals[key]
        elif isinstance(key, Symbol):
            if key in self.sym2sigs and len(self.sym2sigs[key]) == 1:
                return self.sym2sigs[key][0]
        for base in self.scope.bases:
            basemodule = env.hdlscope(base)
            found = basemodule.signal(key)
            if found:
                return found
        return None

    def get_signals(self, include_tags=None, exclude_tags=None, with_base=False):
        if include_tags:
            assert isinstance(include_tags, set)
        if exclude_tags:
            assert isinstance(exclude_tags, set)
        sigs = []
        if with_base:
            for base in self.scope.bases:
                basemodule = env.hdlscope(base)
                sigs.extend(basemodule.get_signals(include_tags, exclude_tags, True))
        for sig in sorted(self.signals.values(), key=lambda sig: sig.name):
            if exclude_tags and exclude_tags & sig.tags:
                continue
            if include_tags:
                ret = include_tags & sig.tags
                if ret:
                    sigs.append(sig)
            else:
                sigs.append(sig)
        return sigs

    def rename_sig(self, old, new):
        assert old in self.signals
        sig = self.signals[old]
        del self.signals[old]
        sig.name = new
        self.signals[new] = sig
        return sig

    def remove_sig(self, sig):
        assert sig.name in self.signals
        del self.signals[sig.name]

    def add_subscope(self, name, hdlscope):
        self.subscope[name] = hdlscope


class HDLModule(HDLScope):
    #Port = namedtuple('Port', ['name', 'width'])
    def __init__(self, scope, name, qualified_name):
        super().__init__(scope, name, qualified_name)
        self._inputs = []
        self._outputs = []
        self.tasks = []
        self.parameters = []
        self.constants = {}
        self.sub_modules = {}
        self.functions = []
        self.decls = defaultdict(list)
        self.fsms = {}
        self.node2if = {}
        self.edge_detectors = set()
        self.ahdl2dfgnode = {}
        self.clock_signal = None

    @classmethod
    def is_hdlmodule_scope(self, scope):
        return ((scope.is_module() and scope.is_instantiated())
                or scope.is_function_module()
                or scope.is_testbench())

    def __str__(self):
        s = '---------------------------------\n'
        s += 'HDLModule {}\n'.format(self.name)
        s += '  -- signals --\n'
        for sig in self.signals.values():
            s += f'{sig.name}[{sig.width}] {sig.tags}\n'
        s += '\n'
        s += '  -- sub modules --\n'
        for name, hdlmodule, connections, param_map in self.sub_modules.values():
            s += '{} \n'.format(name)
            for sig, acc in connections:
                s += '    connection : .{}({}) \n'.format(sig.name, acc.name)
        s += '  -- declarations --\n'
        for tag, decls in self.decls.items():
            s += 'tag : {}\n'.format(tag)
            for decl in decls:
                s += '  {}\n'.format(decl)
        s += '\n'
        s += '  -- fsm --\n'
        for name, fsm in self.fsms.items():
            s += '---------------------------------\n'
            s += 'fsm : {}\n'.format(name)
            for stg in fsm.stgs:
                for state in stg.states:
                    s += str(state)
        s += '\n'
        return s

    def __repr__(self):
        return self.name

    def add_input(self, sig):
        self._inputs.append(sig)

    def inputs(self):
        return self._inputs

    def add_output(self, sig):
        self._outputs.append(sig)

    def outputs(self):
        return self._outputs

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

    def add_sub_module(self, name, hdlmodule, connections, param_map=None):
        assert isinstance(name, str)
        self.sub_modules[name] = (name, hdlmodule, connections, param_map)

    def add_function(self, func, tag=''):
        assert isinstance(func, AHDL_FUNCTION)
        self.functions.append(func)

    def add_fsm(self, fsm_name, scope):
        self.fsms[fsm_name] = FSM(fsm_name, scope)

    def add_fsm_state_var(self, fsm_name, var):
        assert fsm_name in self.fsms
        self.fsms[fsm_name].state_var = var

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

    def add_edge_detector(self, sig, old, new):
        self.edge_detectors.add((sig, old, new))

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
