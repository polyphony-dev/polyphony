from logging import getLogger, DEBUG
logger = getLogger(__name__)

class HDLModuleInfo:
    #Port = namedtuple('Port', ['name', 'width'])
    def __init__(self, name, qualified_name):
        self.name = name
        self.qualified_name = qualified_name[len('@top')+1:].replace('.', '_')
        self.inputs = []
        self.outputs = []
        self.parameters = []
        self.constants = []
        self.internal_regs = set()
        self.internal_reg_arrays = []
        self.internal_wires =set()
        self.sub_modules = []
        self.static_assignments = []
        self.functions = []
        self.muxes = []
        self.demuxes = []


    def __str__(self):
        s = 'ModuleInfo {}\n'.format(self.name)
        s += '  -- num of signals --\n'
        s += '  - num of inputs ' + str(len(self.inputs))
        s += '\n'
        s += '  - num of outputs ' + str(len(self.outputs))
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
        s += '  - inputs\n    ' + ', '.join(['{} {}[{}:0]'.format(name, typ, width-1) for name, typ, width in self.inputs])
        s += '\n'
        s += '  - outputs\n    ' + ', '.join(['{} {}[{}:0]'.format(name, typ, width-1) for name, typ, width in self.outputs])
        s += '\n'
        s += '  - constants\n    ' + ', '.join(['{}={}'.format(name, value) for name, value in self.constants])
        s += '\n'
        s += '  - internal_regs\n    ' + ', '.join(['{} {}[{}:0]'.format(sign, name, width-1) for name, width, sign in self.internal_regs])
        s += '\n'
        s += '  - internal_reg_arrays\n    ' + ', '.join(['{} {}[{}:0][0:{}]'.format(sign, name, width-1, size-1) for name, width, size, sign in self.internal_reg_arrays])
        s += '\n'
        s += '  - internal_wires\n    ' + ', '.join(['{} {}[{}:0]'.format(sign, name, width-1) for name, width, sign in self.internal_wires])
        s += '\n'

        s += '  - sub modules\n    ' + ', '.join([name for name, info, port_map, param_map in self.sub_modules])
        s += '\n'
        s += '  - functions\n    ' + ', '.join([str(f.output.sym.name) for f in self.functions])
        s += '\n'

        return s

    def add_input(self, name, typ, bit_width):
        self.inputs.append((name, typ, bit_width))

    def add_output(self, name, typ, bit_width):
        self.outputs.append((name, typ, bit_width))

    def add_constant(self, name, value):
        self.constants.append((name, value))

    def add_internal_reg(self, name, bit_width, sign='signed'):
        self.internal_regs.add((name, bit_width, sign))

    def add_internal_reg_array(self, name, bit_width, size, sign='signed'):
        self.internal_reg_arrays.append((name, bit_width, size, sign))

    def add_internal_wire(self, name, bit_width, sign='signed'):
        self.internal_wires.add((name, bit_width, sign))

    def add_static_assignment(self, assign):
        self.static_assignments.append(assign)

    def add_sub_module(self, name, module_info, port_map, param_map=None):
        ''' 
        port_map := key=port_name : value=(signal_name, 'I'|'O', width, shadow) 
        '''
        if name in [name for name, info, port_map, param_map in self.sub_modules]:
            logger.debug(name + ' is already added')
            return
        self.sub_modules.append((name, module_info, port_map, param_map))

    def add_function(self, func):
        self.functions.append(func)

    def add_mux(self, mux):
        self.muxes.append(mux)

    def add_demux(self, demux):
        self.demuxes.append(demux)
