from collections import defaultdict
from logging import getLogger, DEBUG
from .hdlinterface import *
from . import libs
from .env import env
from .ahdl import *

logger = getLogger(__name__)

class FSM:
    def __init__(self):
        self.name = None
        self.state_var = None
        self.stgs = None
        self.outputs = set()

class HDLModuleInfo:
    #Port = namedtuple('Port', ['name', 'width'])
    def __init__(self, scope, name, qualified_name):
        self.scope = scope
        self.name = name
        self.qualified_name = qualified_name[len('@top')+1:].replace('.', '_')
        self.interfaces = []
        self.interconnects = []
        self.parameters = []
        self.constants = []
        self.state_constants = []
        self.sub_modules = {}
        self.functions = []
        self.muxes = []
        self.demuxes = []
        self.decls = defaultdict(list)
        self.class_fields = set()
        self.internal_field_accesses = {}
        self.fsms = defaultdict(FSM)
        self.node2if = {}

    def __str__(self):
        s = 'ModuleInfo {}\n'.format(self.name)
        s += '  -- num of signals --\n'
        s += '  - sub modules\n    ' + ', '.join([name for name, _, _, _, _ in self.sub_modules.values()])
        s += '\n'
        s += '  - functions\n    ' + ', '.join([str(f.output.sig.name) for f in self.functions])
        s += '\n'

        return s

    def __repr__(self):
        return self.name

    def add_interface(self, interface):
        self.interfaces.append(interface)

    def add_interconnect(self, interconnect):
        self.interconnects.append(interconnect)

    def add_constant(self, name, value):
        assert isinstance(name, str)
        self.constants.append((name, value))

    def add_state_constant(self, name, value):
        assert isinstance(name, str)
        self.state_constants.append((name, value))

    def add_internal_reg(self, sig, tag=''):
        assert not sig.is_net()
        self.add_decl(tag, AHDL_REG_DECL(sig))

    def add_internal_reg_array(self, sig, size, tag=''):
        assert not sig.is_net()
        self.add_decl(tag, AHDL_REG_ARRAY_DECL(sig, size))

    def add_internal_net(self, sig, tag=''):
        assert not sig.is_reg()
        self.add_decl(tag, AHDL_NET_DECL(sig))

    def add_internal_net_array(self, sig, size, tag=''):
        assert not sig.is_reg()
        self.add_decl(tag, AHDL_NET_ARRAY_DECL(sig, size))

    def remove_internal_net(self, sig):
        assert isinstance(sig, Signal)
        removes = []
        for tag, decls in self.decls.items():
            for decl in decls:
                if isinstance(decl, AHDL_NET_DECL):
                    if decl.sig == sig:
                        removes.append((tag, decl))
        for tag, decl in removes:
            self.remove_decl(tag, decl)


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
        self.decls[tag].append(decl)

    def remove_decl(self, tag, decl):
        assert isinstance(decl, AHDL_DECL)
        self.decls[tag].remove(decl)

    def add_sub_module(self, name, module_info, accessors, param_map=None):
        assert isinstance(name, str)
        is_public = self.scope.is_class()
        sub_infs = defaultdict(list)
        for inf in accessors:
            if not inf.is_public:
                continue
            if module_info.scope and module_info.scope.is_class():
                fieldif = InstanceInterface(inf, name, module_info.scope, is_public=is_public)
                self.add_interface(fieldif)
                sub_infs[inf.name].append(fieldif)
            else:
                fieldif = inf.clone()
                if fieldif.name:
                    fieldif.name = name + '_' + fieldif.name
                else:
                    fieldif.name = name
                fieldif.is_public = False
                sub_infs[inf.name].append(fieldif)
        self.sub_modules[name] = (name, module_info, accessors, sub_infs, param_map)

    def add_function(self, func, tag=''):
        self.add_decl(tag, func)

    def add_mux(self, mux, tag=''):
        assert isinstance(mux, AHDL_MUX)
        self.add_decl(tag, mux)

    def add_demux(self, demux, tag=''):
        assert isinstance(demux, AHDL_DEMUX)
        self.add_decl(tag, demux)

    def add_class_field(self, field):
        assert field.is_field()
        self.class_fields.add(field)

    def add_internal_field_access(self, field_name, access):
        assert isinstance(field_name, str)
        self.internal_field_accesses[field_name] = access

    def add_fsm_state_var(self, fsm_name, var):
        self.fsms[fsm_name].name = fsm_name
        self.fsms[fsm_name].state_var = var

    def add_fsm_stg(self, fsm_name, stgs):
        self.fsms[fsm_name].stgs = stgs

    def add_fsm_output(self, fsm_name, output_sig):
        self.fsms[fsm_name].outputs.add(output_sig)


class RAMModuleInfo(HDLModuleInfo):
    def __init__(self, name, data_width, addr_width):
        super().__init__(None, 'ram', '@top'+'.BidirectionalSinglePortRam')
        self.ramif = RAMInterface('', data_width, addr_width, is_public=True)
        self.add_interface(self.ramif)
        env.add_using_lib(libs.bidirectional_single_port_ram)
