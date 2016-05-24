from collections import defaultdict
from logging import getLogger, DEBUG
logger = getLogger(__name__)

class FSM:
    def __init__(self):
        self.name = None
        self.state_var = None
        self.stgs = None
        self.outputs = set()

class HDLModuleInfo:
    #Port = namedtuple('Port', ['name', 'width'])
    def __init__(self, name, qualified_name):
        self.name = name
        self.qualified_name = qualified_name[len('@top')+1:].replace('.', '_')
        self.data_inputs = {}
        self.data_outputs = {}
        self.ctrl_inputs = {}
        self.ctrl_outputs = {}
        self.mem_inputs = {}
        self.mem_outputs = {}
        self.parameters = []
        self.constants = []
        self.internal_regs = set()
        self.internal_reg_arrays = []
        self.internal_wires =set()
        self.sub_modules = {}
        self.static_assignments = []
        self.sync_assignments = []
        self.functions = []
        self.muxes = []
        self.demuxes = []
        self.class_fields = set()
        self.field_accesses = {}
        self.fsms = defaultdict(FSM)

    def __str__(self):
        s = 'ModuleInfo {}\n'.format(self.name)
        s += '  -- num of signals --\n'
        s += '  - num of data inputs ' + str(len(self.data_inputs))
        s += '\n'
        s += '  - num of data outputs ' + str(len(self.data_outputs))
        s += '\n'
        s += '  - num of constants ' + str(len(self.constants))
        s += '\n'
        s += '  - num of internal_regs ' + str(len(self.internal_regs))
        s += '\n'
        s += '  - num of internal_reg_arrays ' + str(len(self.internal_reg_arrays))
        s += '\n'
        s += '  - num of internal_wires ' + str(len(self.internal_wires))
        s += '\n'
        s += '  - num of sub modules ' + str(len(self.sub_modules))
        s += '\n'
        s += '  - inputs\n    ' + ', '.join(['{} [{}:0]'.format(sig.name, sig.width-1) for sig in self.data_inputs.values()])
        s += '\n'
        s += '  - outputs\n    ' + ', '.join(['{} [{}:0]'.format(sig.name, sig.width-1) for sig in self.data_outputs.values()])
        s += '\n'
        s += '  - constants\n    ' + ', '.join(['{}={}'.format(name, value) for name, value in self.constants])
        s += '\n'
        s += '  - internal_regs\n    ' + ', '.join(['{}[{}:0]'.format(sig.name, sig.width-1) for sig in self.internal_regs])
        s += '\n'
        s += '  - internal_reg_arrays\n    ' + ', '.join(['{}[{}:0][0:{}]'.format(sig.name, sig.width-1, size-1) for sig, size in self.internal_reg_arrays])
        s += '\n'
        s += '  - internal_wires\n    ' + ', '.join(['{}[{}:0]'.format(sig.name, sig.width-1) for sig in self.internal_wires])
        s += '\n'

        s += '  - sub modules\n    ' + ', '.join([name for name, info, port_map, param_map in self.sub_modules.values()])
        s += '\n'
        s += '  - functions\n    ' + ', '.join([str(f.output.sig.name) for f in self.functions])
        s += '\n'

        return s

    def add_data_input(self, sig):
        self.data_inputs[sig.name] = sig

    def add_data_output(self, sig):
        self.data_outputs[sig.name] = sig

    def add_ctrl_input(self, sig):
        self.ctrl_inputs[sig.name] = sig

    def add_ctrl_output(self, sig):
        self.ctrl_outputs[sig.name] = sig

    def add_mem_input(self, sig):
        self.mem_inputs[sig.name] = sig

    def add_mem_output(self, sig):
        self.mem_outputs[sig.name] = sig

    def add_constant(self, name, value):
        assert isinstance(name, str)
        self.constants.append((name, value))

    def add_internal_reg(self, sig):
        assert not sig.is_wire()
        self.internal_regs.add(sig)

    def add_internal_reg_array(self, sig, size):
        assert not sig.is_wire()
        self.internal_reg_arrays.append((sig, size))

    def add_internal_wire(self, sig):
        assert not sig.is_reg()
        self.internal_wires.add(sig)

    def add_static_assignment(self, assign):
        self.static_assignments.append(assign)

    def add_sync_assignment(self, assign):
        self.sync_assignments.append(assign)

    def add_sub_module(self, name, module_info, port_map, param_map=None):
        assert isinstance(name, str)
        assert name not in self.sub_modules
        self.sub_modules[name] = (name, module_info, port_map, param_map)

    def add_function(self, func):
        self.functions.append(func)

    def add_mux(self, mux):
        self.muxes.append(mux)

    def add_demux(self, demux):
        self.demuxes.append(demux)

    def add_class_field(self, field):
        assert field.is_field()
        self.class_fields.add(field)

    def add_field_access(self, field, access):
        assert field.is_field()
        self.field_accesses[field] = access

    def add_fsm_state_var(self, fsm_name, var):
        self.fsms[fsm_name].name = fsm_name
        self.fsms[fsm_name].state_var = var

    def add_fsm_stg(self, fsm_name, stgs):
        self.fsms[fsm_name].stgs = stgs

    def add_fsm_output(self, fsm_name, output_sig):
        self.fsms[fsm_name].outputs.add(output_sig)
