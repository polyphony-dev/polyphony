from collections import namedtuple
from .ahdl import *

Port = namedtuple('Port', ('name', 'width', 'dir', 'signed'))


class InterfaceBase(object):
    def __str__(self):
        ports = ', '.join(['<{}:{}:{}>'.format(p.name, p.width, p.dir)
                           for p in self.ports])
        return self.if_name + ports

    def _flip_direction(self, ports):
        def flip(d):
            return 'in' if d == 'out' else 'out'
        ports = [Port(p.name, p.width, flip(p.dir), p.signed) for p in ports]
        return ports

    def inports(self):
        return [p for p in self.ports if p.dir == 'in']

    def outports(self):
        return [p for p in self.ports if p.dir == 'out']


class Interface(InterfaceBase):
    def __init__(self, if_name, if_owner_name):
        self.if_name = if_name
        self.if_owner_name = if_owner_name
        self.ports = []
        self.signal = None

    def __lt__(self, other):
        return self.if_name < other.if_name

    def port_name(self, port):
        return self._prefixed_port_name(self.if_owner_name, port)

    def _prefixed_port_name(self, prefix, port):
        pfx = prefix + '_' if prefix else ''
        if self.if_name:
            if port.name:
                return pfx + '{}_{}'.format(self.if_name, port.name)
            else:
                return pfx + self.if_name
        else:
            assert port.name
            return pfx + port.name

    def _port_name(self, port):
        if self.if_name:
            if port.name:
                return '{}_{}'.format(self.if_name, port.name)
            else:
                return self.if_name
        else:
            assert port.name
            return port.name

    def regs(self):
        return self.outports()

    def nets(self):
        return self.inports()


class Accessor(InterfaceBase):
    def __init__(self, inf):
        self.acc_name = inf.if_name
        self.inf = inf
        self.ports = []

    def __str__(self):
        ports = ', '.join(['<{}:{}:{}>'.format(p.name, p.width, p.dir)
                           for p in self.ports])
        return self.acc_name + ports

    def port_name(self, port):
        return self.inf.port_name(port)

    def regs(self):
        return self.inports()

    def nets(self):
        return self.outports()


class IOAccessor(Accessor):
    def __init__(self, inf, inst_name):
        super().__init__(inf)
        if inst_name and inf.if_name:
            self.acc_name = '{}_{}'.format(inst_name, inf.if_name)
        elif inf.if_name:
            self.acc_name = inf.if_name
        else:
            self.acc_name = inst_name
        self.inst_name = inst_name

    def port_name(self, port):
        if self.inst_name:
            return '{}_{}'.format(self.inst_name, self.inf.port_name(port))
        else:
            return self.inf.port_name(port)


def single_read_seq(signal, name, step, dst):
    # blocking if the port is not 'valid'
    if signal.is_valid_protocol() or signal.is_ready_valid_protocol():
        if step == 0:
            ports = [AHDL_SYMBOL(name + '_valid')]
            return (AHDL_META_WAIT('WAIT_VALUE', AHDL_CONST(1), *ports), )
        elif step == 1:
            # Note that reading from the port is in the next scheduling time of the wait function
            # However, in fact reading is doing on the same time of the wait function by merging process
            if signal.is_ready_valid_protocol():
                return (AHDL_MOVE(AHDL_SYMBOL(name + '_ready'), AHDL_CONST(1)),
                        AHDL_MOVE(dst, AHDL_SYMBOL(name)))
            else:
                return (AHDL_MOVE(dst, AHDL_SYMBOL(name)), )
        elif step == 2:
            assert signal.is_ready_valid_protocol()
            return (AHDL_MOVE(AHDL_SYMBOL(name + '_ready'),
                              AHDL_CONST(0)), )
    else:
        if step == 0:
            return (AHDL_MOVE(dst, AHDL_SYMBOL(name)), )


def single_write_seq(signal, name, step, src):
    if signal.is_valid_protocol() or signal.is_ready_valid_protocol():
        if step == 0:
            if signal.is_ready_valid_protocol():
                ports = [AHDL_SYMBOL(name + '_ready')]
                return (AHDL_MOVE(AHDL_SYMBOL(name), src),
                        AHDL_MOVE(AHDL_SYMBOL(name + '_valid'), AHDL_CONST(1)),
                        AHDL_META_WAIT('WAIT_VALUE', AHDL_CONST(1), *ports))
            else:
                return (AHDL_MOVE(AHDL_SYMBOL(name), src),
                        AHDL_MOVE(AHDL_SYMBOL(name + '_valid'), AHDL_CONST(1)))
        elif step == 1:
            return (AHDL_MOVE(AHDL_SYMBOL(name + '_valid'), AHDL_CONST(0)), )
    else:
        if step == 0:
            return (AHDL_MOVE(AHDL_SYMBOL(name), src), )


class SinglePortInterface(Interface):
    def __init__(self, signal):
        super().__init__(signal.name, '')
        self.signal = signal
        self.data_width = signal.width

    def port_name(self, port):
        if port.name:
            return '{}_{}'.format(self.if_name, port.name)
        else:
            return self.if_name


class SingleReadInterface(SinglePortInterface):
    def __init__(self, signal):
        super().__init__(signal)
        signed = True if signal.is_int() else False
        self.ports.append(Port('', self.data_width, 'in', signed))
        if signal.is_valid_protocol():
            self.ports.append(Port('valid', 1, 'in', False))
        elif signal.is_ready_valid_protocol():
            self.ports.append(Port('valid', 1, 'in', False))
            self.ports.append(Port('ready', 1, 'out', False))

    def accessor(self, inst_name=''):
        acc = SingleWriteAccessor(self, inst_name)
        return acc

    def reset_stms(self):
        stms = []
        if self.signal.is_ready_valid_protocol():
            stms.append(AHDL_MOVE(AHDL_SYMBOL(self.signal.name + '_ready'),
                                  AHDL_CONST(0)))
        return stms

    def read_sequence(self, step, dst):
        return single_read_seq(self.signal, self.if_name, step, dst)


class SingleWriteInterface(SinglePortInterface):
    def __init__(self, signal):
        super().__init__(signal)
        #assert signal.is_output()
        signed = True if signal.is_int() else False
        self.ports.append(Port('', self.data_width, 'out', signed))
        if signal.is_valid_protocol():
            self.ports.append(Port('valid', 1, 'out', False))
        elif signal.is_ready_valid_protocol():
            self.ports.append(Port('valid', 1, 'out', False))
            self.ports.append(Port('ready', 1, 'in', False))

    def accessor(self, inst_name=''):
        acc = SingleReadAccessor(self, inst_name)
        return acc

    def reset_stms(self):
        stms = []
        if hasattr(self.signal, 'init_value'):
            iv = self.signal.init_value
        else:
            iv = 0
        stms.append(AHDL_MOVE(AHDL_SYMBOL(self.signal.name),
                              AHDL_CONST(iv)))
        if self.signal.is_valid_protocol() or self.signal.is_ready_valid_protocol():
            stms.append(AHDL_MOVE(AHDL_SYMBOL(self.signal.name + '_valid'),
                                  AHDL_CONST(0)))
        return stms

    def write_sequence(self, step, src):
        return single_write_seq(self.signal, self.if_name, step, src)


class SingleReadAccessor(IOAccessor):
    def __init__(self, inf, inst_name):
        super().__init__(inf, inst_name)
        self.ports = inf.ports[:]

    def reset_stms(self):
        stms = []
        signal = self.inf.signal
        if signal.is_ready_valid_protocol():
            stms.append(AHDL_MOVE(AHDL_SYMBOL(self.acc_name + '_ready'),
                                  AHDL_CONST(0)))
        return stms

    def read_sequence(self, step, dst):
        return single_read_seq(self.inf.signal, self.acc_name, step, dst)


class SingleWriteAccessor(IOAccessor):
    def __init__(self, inf, inst_name):
        super().__init__(inf, inst_name)
        self.ports = inf.ports[:]

    def reset_stms(self):
        stms = []
        signal = self.inf.signal
        if hasattr(signal, 'init_value'):
            iv = signal.init_value
        else:
            iv = 0
        stms.append(AHDL_MOVE(AHDL_SYMBOL(self.acc_name),
                              AHDL_CONST(iv)))
        if signal.is_valid_protocol() or signal.is_ready_valid_protocol():
            stms.append(AHDL_MOVE(AHDL_SYMBOL(self.acc_name + '_valid'),
                                  AHDL_CONST(0)))
        return stms

    def write_sequence(self, step, src):
        return single_write_seq(self.inf.signal, self.acc_name, step, src)


class FunctionInterface(Interface):
    def __init__(self, name, owner_name=''):
        super().__init__(name, owner_name)
        self.ports.append(Port('ready', 1, 'in', False))
        self.ports.append(Port('accept', 1, 'in', False))
        self.ports.append(Port('valid', 1, 'out', False))

    def add_data_in(self, din_name, width, signed):
        self.ports.append(Port(din_name, width, 'in', signed))

    def add_data_out(self, dout_name, width, signed):
        self.ports.append(Port(dout_name, width, 'out', signed))

    def accessor(self, inst_name=''):
        acc = FunctionAccessor(self, inst_name)
        return acc

    def reset_stms(self):
        stms = []
        for p in self.outports():
            stms.append(AHDL_MOVE(AHDL_SYMBOL(self.port_name(p)),
                                  AHDL_CONST(0)))
        return stms


class FunctionAccessor(IOAccessor):
    def __init__(self, inf, inst_name):
        super().__init__(inf, inst_name)
        self.ports = inf.ports[:]

    def port_name(self, port):
        assert self.inst_name
        return '{}_{}'.format(self.inst_name, self.inf._port_name(port))


class RAMModuleInterface(Interface):
    def __init__(self, name, data_width, addr_width):
        super().__init__(name, '')
        self.data_width = data_width
        self.addr_width = addr_width
        self.ports.append(Port('addr', addr_width, 'in', True))
        self.ports.append(Port('d',    data_width, 'in', True))
        self.ports.append(Port('we',   1,          'in', False))
        self.ports.append(Port('q',    data_width, 'out', True))
        self.ports.append(Port('len',  addr_width, 'out', False))

    def accessor(self, inst_name=''):
        return RAMModuleAccessor(self, inst_name)


class RAMModuleAccessor(IOAccessor):
    def __init__(self, inf, inst_name):
        super().__init__(inf, inst_name)
        self.ports = inf.ports[:]

    def regs(self):
        return []

    def nets(self):
        return self.ports


class RAMBridgeInterface(Interface):
    def __init__(self, name, owner_name, data_width, addr_width):
        super().__init__(name, owner_name)
        self.data_width = data_width
        self.addr_width = addr_width
        self.ports.append(Port('addr', addr_width, 'in', True))
        self.ports.append(Port('d',    data_width, 'in', True))
        self.ports.append(Port('we',   1,          'in', False))
        self.ports.append(Port('q',    data_width, 'out', True))
        self.ports.append(Port('len',  addr_width, 'out', False))
        self.ports.append(Port('req',  addr_width, 'in', False))

    def accessor(self, inst_name=''):
        return RAMBridgeAccessor(self, inst_name)

    def regs(self):
        return []

    def nets(self):
        ports = self.ports[:]
        return self._flip_direction(ports)

    def reset_stms(self):
        return []


class RAMBridgeAccessor(IOAccessor):
    def __init__(self, inf, inst_name):
        super().__init__(inf, inst_name)
        self.ports = inf.ports[:]

    def port_name(self, port):
        if self.inst_name:
            return '{}_{}'.format(self.inst_name, self.inf._port_name(port))
        else:
            return self.inf.port_name(port)

    def regs(self):
        return []

    def nets(self):
        return self.ports


class RAMAccessor(Accessor):
    def __init__(self, signal, data_width, addr_width, is_sink=True):
        inf = Interface(signal.name, '')
        inf.signal = signal
        super().__init__(inf)
        self.data_width = data_width
        self.addr_width = addr_width
        self.is_sink = is_sink
        self.ports.append(Port('addr', addr_width, 'in', True))
        self.ports.append(Port('d',    data_width, 'in', True))
        self.ports.append(Port('we',   1,          'in', False))
        self.ports.append(Port('q',    data_width, 'out', True))
        self.ports.append(Port('len',  addr_width, 'out', False))
        self.ports.append(Port('req',  1,          'in', False))

    def regs(self):
        if self.is_sink:
            return self.inports()
        else:
            return []

    def nets(self):
        if self.is_sink:
            return self.outports()
        else:
            return self.ports

    def reset_stms(self):
        stms = []
        for p in self.inports():
            stms.append(AHDL_MOVE(AHDL_SYMBOL(self.port_name(p)),
                                  AHDL_CONST(0)))
        return stms

    def read_sequence(self, step, offset, dst, is_continuous):
        name = self.acc_name
        if step == 0:
            return (AHDL_MOVE(AHDL_SYMBOL(name + '_addr'), offset),
                    AHDL_MOVE(AHDL_SYMBOL(name + '_we'), AHDL_CONST(0)),
                    AHDL_MOVE(AHDL_SYMBOL(name + '_req'), AHDL_CONST(1)))
        elif step == 1:
            return (AHDL_NOP('wait for output of {}'.format(name)), )
        elif step == 2:
            if is_continuous:
                return (AHDL_MOVE(dst, AHDL_SYMBOL(name + '_q')), )
            else:
                return (AHDL_MOVE(dst, AHDL_SYMBOL(name + '_q')),
                        AHDL_MOVE(AHDL_SYMBOL(name + '_req'), AHDL_CONST(0)))

    def write_sequence(self, step, offset, src, is_continuous):
        name = self.acc_name
        if step == 0:
            return (AHDL_MOVE(AHDL_SYMBOL(name + '_addr'), offset),
                    AHDL_MOVE(AHDL_SYMBOL(name + '_we'), AHDL_CONST(1)),
                    AHDL_MOVE(AHDL_SYMBOL(name + '_req'), AHDL_CONST(1)),
                    AHDL_MOVE(AHDL_SYMBOL(name + '_d'), src))
        elif step == 1:
            if is_continuous:
                return tuple()
            else:
                return (AHDL_MOVE(AHDL_SYMBOL(name + '_req'), AHDL_CONST(0)), )


class RegArrayInterface(Interface):
    def __init__(self, name, owner_name, data_width, length):
        super().__init__(name, owner_name)
        self.data_width = data_width
        self.length = length
        for i in range(length):
            pname = '{}'.format(i)
            self.ports.append(Port(pname, data_width, 'in', True))

    def accessor(self, inst_name=''):
        return RegArrayAccessor(self, inst_name)

    def port_name(self, port):
        return '{}_{}{}'.format(self.if_owner_name, self.if_name, port.name)

    def reset_stms(self):
        return []


class RegArrayAccessor(IOAccessor):
    def __init__(self, inf, inst_name):
        super().__init__(inf, inst_name)
        self.ports = inf.ports[:]

    def port_name(self, port):
        return '{}{}'.format(self.acc_name, port.name)

    def regs(self):
        return []

    def nets(self):
        return self.ports


def fifo_read_seq(name, step, dst):
    if step == 0:
        ports = [AHDL_SYMBOL(name + '_empty')]
        return (AHDL_META_WAIT('WAIT_VALUE', AHDL_CONST(0), *ports), )
    elif step == 1:
        q_read = AHDL_SYMBOL(name + '_read')
        return (AHDL_MOVE(q_read, AHDL_CONST(1)), )
    elif step == 2:
        q_read = AHDL_SYMBOL(name + '_read')
        q_dout = AHDL_SYMBOL(name + '_dout')
        return (AHDL_MOVE(q_read, AHDL_CONST(0)),
                AHDL_MOVE(dst, q_dout))


def fifo_write_seq(name, step, src):
    if step == 0:
        ports = [AHDL_SYMBOL(name + '_full')]
        return (AHDL_META_WAIT('WAIT_VALUE', AHDL_CONST(0), *ports), )
    elif step == 1:
        q_write = AHDL_SYMBOL(name + '_write')
        q_din = AHDL_SYMBOL(name + '_din')
        return (AHDL_MOVE(q_write, AHDL_CONST(1)),
                AHDL_MOVE(q_din, src))
    elif step == 2:
        q_write = AHDL_SYMBOL(name + '_write')
        return (AHDL_MOVE(q_write, AHDL_CONST(0)), )


class FIFOInterface(Interface):
    def __init__(self, signal):
        super().__init__(signal.name, '')
        self.signal = signal
        self.data_width = signal.width
        self.max_size = signal.maxsize

    def port_name(self, port):
        return self._port_name(port)

    def read_sequence(self, step, dst):
        return fifo_read_seq(self.if_name, step, dst)

    def write_sequence(self, step, src):
        return fifo_write_seq(self.if_name, step, src)

    def reset_stms(self):
        stms = []
        for p in self.outports():
            stms.append(AHDL_MOVE(AHDL_SYMBOL(self.port_name(p)),
                                  AHDL_CONST(0)))
        return stms


class FIFOAccessor(IOAccessor):
    def __init__(self, inf, inst_name):
        super().__init__(inf, inst_name)

    def read_sequence(self, step, dst):
        return fifo_read_seq(self.acc_name, step, dst)

    def write_sequence(self, step, src):
        return fifo_write_seq(self.acc_name, step, src)

    def reset_stms(self):
        stms = []
        for p in self.inports():
            stms.append(AHDL_MOVE(AHDL_SYMBOL(self.port_name(p)),
                                  AHDL_CONST(0)))
        return stms


class FIFOModuleInterface(FIFOInterface):
    def __init__(self, signal):
        super().__init__(signal)
        self.ports.append(Port('din', self.data_width, 'in', True))
        self.ports.append(Port('write', 1, 'in', False))
        self.ports.append(Port('full', 1, 'out', False))
        self.ports.append(Port('dout', self.data_width, 'out', True))
        self.ports.append(Port('read', 1, 'in', False))
        self.ports.append(Port('empty', 1, 'out', False))

    def port_name(self, port):
        return port.name

    def accessor(self, inst_name=''):
        return FIFOModuleAccessor(self, inst_name)


class FIFOModuleAccessor(FIFOAccessor):
    def __init__(self, inf, inst_name):
        super().__init__(inf, inst_name)
        self.ports = inf.ports[:]

    def port_name(self, port):
        return '{}_{}'.format(self.acc_name, port.name)


class FIFOReadInterface(FIFOInterface):
    def __init__(self, signal):
        super().__init__(signal)
        self.ports.append(Port('dout', self.data_width, 'in', True))
        self.ports.append(Port('read', 1, 'out', False))
        self.ports.append(Port('empty', 1, 'in', False))

    def accessor(self, inst_name=''):
        return FIFOWriteAccessor(self, inst_name)


class FIFOWriteInterface(FIFOInterface):
    def __init__(self, signal):
        super().__init__(signal)
        self.ports.append(Port('din', self.data_width, 'out', True))
        self.ports.append(Port('write', 1, 'out', False))
        self.ports.append(Port('full', 1, 'in', False))

    def accessor(self, inst_name=''):
        return FIFOReadAccessor(self, inst_name)


class FIFOReadAccessor(FIFOAccessor):
    def __init__(self, inf, inst_name):
        super().__init__(inf, inst_name)
        data_width = self.inf.data_width
        # reading ports for fifo module interface
        self.ports.append(Port('dout', data_width, 'out', True))
        self.ports.append(Port('read', 1, 'in', False))
        self.ports.append(Port('empty', 1, 'out', False))

    def nets(self):
        ports = list(self.outports())
        # nets for fifo write interface
        ports.append(Port('din', self.inf.data_width, 'out', True))
        ports.append(Port('write', 1, 'out', False))
        ports.append(Port('full', 1, 'out', False))
        return ports


class FIFOWriteAccessor(FIFOAccessor):
    def __init__(self, inf, inst_name):
        super().__init__(inf, inst_name)
        data_width = self.inf.data_width
        # writingg ports for fifo module interface
        self.ports.append(Port('din', data_width, 'in', True))
        self.ports.append(Port('write', 1, 'in', False))
        self.ports.append(Port('full', 1, 'out', False))
        # nets for fifo write interface

    def nets(self):
        ports = list(self.outports())
        # nets for fifo write interface
        ports.append(Port('dout', self.inf.data_width, 'out', True))
        ports.append(Port('read', 1, 'out', False))
        ports.append(Port('empty', 1, 'out', False))
        return ports


class Interconnect(object):
    def __init__(self, name, ins, outs, cs_name=''):
        self.name = name
        self.ins = ins
        self.outs = outs
        self.cs_name = cs_name

    def __str__(self):
        s = self.name + '\n'
        for i in self.ins:
            s += str(i) + '\n'
        for o in self.outs:
            s += str(o) + '\n'
        return s
