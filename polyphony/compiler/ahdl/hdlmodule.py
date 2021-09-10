﻿from collections import defaultdict, OrderedDict
from .hdlinterface import *
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


class HDLModule(object):
    #Port = namedtuple('Port', ['name', 'width'])
    def __init__(self, scope, name, qualified_name):
        self.scope = scope
        self.name = name
        self.qualified_name = qualified_name
        self.signals = {}
        self.interfaces = OrderedDict()
        self.interconnects = []
        self.accessors = {}
        self.parameters = []
        self.constants = []
        self.state_constants = []
        self.sub_modules = {}
        self.functions = []
        self.muxes = []
        self.demuxes = []
        self.decls = defaultdict(list)
        self.internal_field_accesses = {}
        self.fsms = {}
        self.node2if = {}
        self.edge_detectors = set()
        self.ahdl2dfgnode = {}
        self.sig2sym = {}
        self.sym2sigs = defaultdict(list)
        self.clock_signal = None

    def __str__(self):
        s = '---------------------------------\n'
        s += 'HDLModule {}\n'.format(self.name)
        s += '  -- signals --\n'
        for sig in self.signals.values():
            s += f'{sig.name}[{sig.width}] {sig.tags}\n'
        s += '\n'
        s += '  -- interfaces --\n'
        for inf in self.interfaces.values():
            s += '{}\n'.format(inf)
        s += '  -- accessors --\n'
        for acc in self.accessors.values():
            s += '{}\n'.format(acc)
        s += '  -- sub modules --\n'
        for name, hdlmodule, connections, param_map in self.sub_modules.values():
            s += '{} \n'.format(name)
            for conns in connections.values():
                for inf, acc in conns:
                    if acc.connected:
                        s += '    connection : .{}({}) \n'.format(inf.if_name, acc.acc_name)
                    else:
                        s += '    connection : .{}(---) \n'.format(inf.if_name)
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
        s += '\n'.join([str(inf) for inf in self.interfaces.values()])
        return s

    def __repr__(self):
        return self.name

    def add_interface(self, name, interface):
        self.interfaces[name] = interface

    def add_interconnect(self, interconnect):
        self.interconnects.append(interconnect)

    def add_accessor(self, name, accessor):
        self.accessors[name] = accessor

    def add_constant(self, name, value):
        assert isinstance(name, str)
        self.constants.append((name, value))

    def add_state_constant(self, name, value):
        assert isinstance(name, str)
        self.state_constants.append((name, value))

    def add_internal_reg(self, sig, tag=''):
        assert not sig.is_net()
        sig.add_tag('reg')
        self.add_decl(tag, AHDL_SIGNAL_DECL(sig))

    def add_internal_reg_array(self, sig, size, tag=''):
        assert not sig.is_net()
        sig.add_tag('regarray')
        if isinstance(size, int):
            size = AHDL_CONST(size)
        self.add_decl(tag, AHDL_SIGNAL_ARRAY_DECL(sig, size))

    def add_internal_net(self, sig, tag=''):
        assert not sig.is_reg()
        sig.add_tag('net')
        self.add_decl(tag, AHDL_SIGNAL_DECL(sig))

    def add_internal_net_array(self, sig, size, tag=''):
        assert not sig.is_reg()
        sig.add_tag('netarray')
        if isinstance(size, int):
            size = AHDL_CONST(size)
        self.add_decl(tag, AHDL_SIGNAL_ARRAY_DECL(sig, size))

    def remove_internal_net(self, sig):
        assert isinstance(sig, Signal)
        removes = []
        for tag, decls in self.decls.items():
            for decl in decls:
                if isinstance(decl, AHDL_SIGNAL_DECL) and decl.sig == sig and sig.is_net():
                    removes.append((tag, decl))
        for tag, decl in removes:
            self.remove_decl(tag, decl)

    def get_reg_decls(self, with_array=True):
        results = []
        for tag, decls in self.decls.items():
            sigdecls = [decl for decl in decls if decl.is_a(AHDL_SIGNAL_DECL)]
            if not with_array:
                sigdecls = [decl for decl in sigdecls if not decl.is_a(AHDL_SIGNAL_ARRAY_DECL)]
            regdecls = [decl for decl in sigdecls if decl.sig.is_reg()]
            results.append((tag, regdecls))
        return results

    def get_net_decls(self, with_array=True):
        results = []
        for tag, decls in self.decls.items():
            sigdecls = [decl for decl in decls if decl.is_a(AHDL_SIGNAL_DECL)]
            if not with_array:
                sigdecls = [decl for decl in sigdecls if not decl.is_a(AHDL_SIGNAL_ARRAY_DECL)]
            netdecls = [decl for decl in sigdecls if decl.sig.is_net()]
            results.append((tag, netdecls))
        return results

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
                if isinstance(decl, AHDL_SIGNAL_DECL) and decl.sig is sig:
                    self.remove_decl(tag, decl)
                elif isinstance(decl, AHDL_ASSIGN):
                    if decl.dst.is_a(AHDL_VAR) and decl.dst.sig is sig:
                        self.remove_decl(tag, decl)
                    elif decl.dst.is_a(AHDL_SUBSCRIPT) and decl.dst.memvar.sig is sig:
                        self.remove_decl(tag, decl)

    def add_sub_module(self, name, hdlmodule, connections, param_map=None):
        assert isinstance(name, str)
        self.sub_modules[name] = (name, hdlmodule, connections, param_map)

    def add_function(self, func, tag=''):
        self.add_decl(tag, func)

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

    def find_interface(self, name):
        if name in self.interfaces:
            return self.interfaces[name]
        assert False

    def resources(self):
        num_of_regs = 0
        num_of_nets = 0
        for inf in self.interfaces.values():
            for r in inf.regs():
                num_of_regs += r.width
            for n in inf.nets():
                num_of_nets += n.width
        for _, decls in self.decls.items():
            for decl in decls:
                if decl.is_a(AHDL_SIGNAL_DECL):
                    if decl.sig.is_reg():
                        num_of_regs += decl.sig.width
                    elif decl.sig.is_net():
                        num_of_nets += decl.sig.width
                elif decl.is_a(AHDL_SIGNAL_ARRAY_DECL):
                    if decl.sig.is_reg():
                        num_of_regs += decl.sig.width * decl.size.value
                    elif decl.sig.is_net():
                        num_of_nets += decl.sig.width * decl.size.value
                elif decl.is_a(AHDL_ASSIGN):
                    decl.src

        num_of_states = 0
        for _, fsm in self.fsms.items():
            for stg in fsm.stgs:
                num_of_states += len(stg.states)
        return num_of_regs, num_of_nets, num_of_states

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
            basemodule = env.hdlmodule(base)
            found = basemodule.signal(key)
            if found:
                return found
        return None

    def get_signals(self):
        signals_ = {}
        for base in self.scope.bases:
            basemodule = env.hdlmodule(base)
            signals_.update(basemodule.get_signals())
        signals_.update(self.signals)
        return signals_

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

    def use_clock_time(self):
        if self.clock_signal is None:
            self.clock_signal = self.gen_sig(f'{self.name}_clktime', 64)
