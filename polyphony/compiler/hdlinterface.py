from collections import namedtuple
from .ahdl import *


Port = namedtuple('Port', ('name', 'width', 'dir', 'signed'))


class Ports(object):
    def __init__(self):
        self.ports = []

    def __str__(self):
        return ', '.join(['<{}:{}:{}>'.format(p.name, p.width, p.dir)
                          for p in self.ports])

    def __getitem__(self, key):
        for p in self.ports:
            if p.name == key:
                return p

    def append(self, port):
        self.ports.append(port)

    def flipped(self):
        def flip(d):
            return 'in' if d == 'out' else 'out'
        return [Port(p.name, p.width, flip(p.dir), p.signed) for p in self.ports]

    def inports(self):
        return [p for p in self.ports if p.dir == 'in']

    def outports(self):
        return [p for p in self.ports if p.dir == 'out']

    def all(self):
        return self.ports

    def clone(self):
        p = Ports()
        p.ports = self.ports[:]
        return p


def port2ahdl(inf, name):
    return AHDL_SYMBOL(inf.port_name(inf.ports[name]))


class Interface(object):
    def __init__(self, if_name, if_owner_name):
        self.if_name = if_name
        self.if_owner_name = if_owner_name
        self.ports = Ports()
        self.signal = None

    def __str__(self):
        return self.if_name + str(self.ports)

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
        return self.ports.outports()

    def nets(self):
        return self.ports.inports()


class Accessor(object):
    def __init__(self, inf):
        self.acc_name = inf.if_name
        self.inf = inf
        self.ports = Ports()

    def __str__(self):
        return self.acc_name + str(self.ports)

    def port_name(self, port):
        return self.inf.port_name(port)

    def regs(self):
        return self.ports.inports()

    def nets(self):
        return self.ports.outports()


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
            return self.inf._prefixed_port_name(self.inst_name, port)
        else:
            return self.inf.port_name(port)


def single_read_seq(inf, signal, step, dst):
    # blocking if the port is not 'valid'
    data = port2ahdl(inf, '')
    if signal.is_valid_protocol() or signal.is_ready_valid_protocol():
        valid = port2ahdl(inf, 'valid')
        if signal.is_ready_valid_protocol():
            ready = port2ahdl(inf, 'ready')

        if step == 0:
            if signal.is_ready_valid_protocol():
                ports = [valid, ready]
                return (AHDL_MOVE(ready, AHDL_CONST(1)),
                        AHDL_META_WAIT('WAIT_VALUE', AHDL_CONST(1), *ports))
            else:
                ports = [valid]
                return (AHDL_META_WAIT('WAIT_VALUE', AHDL_CONST(1), *ports), )
        elif step == 1:
            if signal.is_ready_valid_protocol():
                return (AHDL_MOVE(dst, data),
                        AHDL_MOVE(ready, AHDL_CONST(0)))
            else:
                return (AHDL_MOVE(dst, data), )
    else:
        if step == 0:
            return (AHDL_MOVE(dst, data), )


def single_write_seq(inf, signal, step, src):
    data = port2ahdl(inf, '')
    if signal.is_valid_protocol() or signal.is_ready_valid_protocol():
        valid = port2ahdl(inf, 'valid')
        if signal.is_ready_valid_protocol():
            ready = port2ahdl(inf, 'ready')
        if step == 0:
            if signal.is_ready_valid_protocol():
                ports = [valid, ready]
                return (AHDL_MOVE(data, src),
                        AHDL_MOVE(valid, AHDL_CONST(1)),
                        AHDL_META_WAIT('WAIT_VALUE', AHDL_CONST(1), *ports))
            else:
                return (AHDL_MOVE(data, src),
                        AHDL_MOVE(valid, AHDL_CONST(1)))
        elif step == 1:
            return (AHDL_MOVE(valid, AHDL_CONST(0)), )
    else:
        if step == 0:
            return (AHDL_MOVE(data, src), )


class SinglePortInterface(Interface):
    def __init__(self, signal, if_name, if_owner_name):
        super().__init__(if_name, if_owner_name)
        self.signal = signal
        self.data_width = signal.width


class SingleReadInterface(SinglePortInterface):
    def __init__(self, signal, if_name='', if_owner_name=''):
        if if_name:
            super().__init__(signal, if_name, if_owner_name)
        else:
            super().__init__(signal, signal.name, if_owner_name)
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
            ready = port2ahdl(self, 'ready')
            stms.append(AHDL_MOVE(ready, AHDL_CONST(0)))
        return stms

    def read_sequence(self, step, dst):
        return single_read_seq(self, self.signal, step, dst)


class SingleWriteInterface(SinglePortInterface):
    def __init__(self, signal, if_name='', if_owner_name=''):
        if if_name:
            super().__init__(signal, if_name, if_owner_name)
        else:
            super().__init__(signal, signal.name, if_owner_name)
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
            valid = port2ahdl(self, 'valid')
            stms.append(AHDL_MOVE(valid, AHDL_CONST(0)))
        return stms

    def write_sequence(self, step, src):
        return single_write_seq(self, self.signal, step, src)


class SingleReadAccessor(IOAccessor):
    def __init__(self, inf, inst_name):
        super().__init__(inf, inst_name)
        self.ports = inf.ports.clone()

    def reset_stms(self):
        stms = []
        signal = self.inf.signal

        if signal.is_ready_valid_protocol():
            ready = port2ahdl(self, 'ready')
            stms.append(AHDL_MOVE(ready, AHDL_CONST(0)))
        return stms

    def read_sequence(self, step, dst):
        return single_read_seq(self, self.inf.signal, step, dst)


class SingleWriteAccessor(IOAccessor):
    def __init__(self, inf, inst_name):
        super().__init__(inf, inst_name)
        self.ports = inf.ports.clone()

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
            valid = port2ahdl(self, 'valid')
            stms.append(AHDL_MOVE(valid, AHDL_CONST(0)))
        return stms

    def write_sequence(self, step, src):
        return single_write_seq(self, self.inf.signal, step, src)


class CallInterface(Interface):
    def __init__(self, name, owner_name=''):
        super().__init__(name, owner_name)
        self.ports.append(Port('ready', 1, 'in', False))
        self.ports.append(Port('accept', 1, 'in', False))
        self.ports.append(Port('valid', 1, 'out', False))

    def accessor(self, inst_name=''):
        acc = CallAccessor(self, inst_name)
        return acc

    def reset_stms(self):
        stms = []
        for p in self.ports.outports():
            stms.append(AHDL_MOVE(AHDL_SYMBOL(self.port_name(p)),
                                  AHDL_CONST(0)))
        return stms

    def callee_prolog(self, step, name):
        if step == 0:
            valid = port2ahdl(self, 'valid')
            ready = port2ahdl(self, 'ready')

            unset_valid = AHDL_MOVE(valid, AHDL_CONST(0))
            ports = [ready]
            wait_ready = AHDL_META_WAIT("WAIT_VALUE", AHDL_CONST(1), *ports)
            return (unset_valid, wait_ready)

    def callee_epilog(self, step, name):
        if step == 0:
            valid = port2ahdl(self, 'valid')
            accept = port2ahdl(self, 'accept')

            set_valid = AHDL_MOVE(valid, AHDL_CONST(1))
            ports = [accept]
            wait_accept = AHDL_META_WAIT("WAIT_VALUE", AHDL_CONST(1), *ports)
            return (set_valid, wait_accept)


class CallAccessor(IOAccessor):
    def __init__(self, inf, inst_name):
        super().__init__(inf, inst_name)
        self.ports = inf.ports.clone()

    def port_name(self, port):
        assert self.inst_name
        return '{}_{}'.format(self.inst_name, self.inf._port_name(port))

    def reset_stms(self):
        stms = []
        for p in self.ports.inports():
            stms.append(AHDL_MOVE(AHDL_SYMBOL(self.port_name(p)),
                                  AHDL_CONST(0)))
        return stms

    def call_sequence(self, step, step_n, argaccs, retaccs, ahdl_call, scope):
        seq = []
        valid = port2ahdl(self, 'valid')
        ready = port2ahdl(self, 'ready')
        accept = port2ahdl(self, 'accept')

        if step == 0:
            seq = [AHDL_MOVE(ready, AHDL_CONST(1))]
            for acc, arg in zip(argaccs, ahdl_call.args):
                if arg.is_a(AHDL_MEMVAR):
                    continue
                seq.extend(acc.write_sequence(0, arg))
        elif step == 1:
            seq = [AHDL_MOVE(ready, AHDL_CONST(0))]

        if step == step_n - 3:
            ports = [valid]
            seq.append(AHDL_META_WAIT('WAIT_VALUE', AHDL_CONST(1), *ports))
        elif step == step_n - 2:
            for acc, ret in zip(retaccs, ahdl_call.returns):
                seq.extend(acc.read_sequence(0, ret))
            seq.append(AHDL_MOVE(accept, AHDL_CONST(1)))
        elif step == step_n - 1:
            seq.append(AHDL_MOVE(accept, AHDL_CONST(0)))
        return tuple(seq)


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
        self.ports = inf.ports.clone()

    def regs(self):
        return []

    def nets(self):
        return self.ports.all()


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
        self.ports.append(Port('req',  1,          'in', False))

    def accessor(self, inst_name=''):
        return RAMBridgeAccessor(self, inst_name)

    def regs(self):
        return []

    def nets(self):
        return self.ports.flipped()

    def reset_stms(self):
        return []


class RAMBridgeAccessor(IOAccessor):
    def __init__(self, inf, inst_name):
        super().__init__(inf, inst_name)
        self.ports = inf.ports.clone()

    def port_name(self, port):
        if self.inst_name:
            return '{}_{}'.format(self.inst_name, self.inf._port_name(port))
        else:
            return self.inf.port_name(port)

    def regs(self):
        return []

    def nets(self):
        return self.ports.all()

    def reset_stms(self):
        return []


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
            return self.ports.inports()
        else:
            return []

    def nets(self):
        if self.is_sink:
            return self.ports.outports()
        else:
            return self.ports.all()

    def reset_stms(self):
        stms = []
        for p in self.ports.inports():
            stms.append(AHDL_MOVE(AHDL_SYMBOL(self.port_name(p)),
                                  AHDL_CONST(0)))
        return stms

    def read_sequence(self, step, offset, dst, is_continuous):
        addr = port2ahdl(self, 'addr')
        we = port2ahdl(self, 'we')
        req = port2ahdl(self, 'req')
        q = port2ahdl(self, 'q')

        if step == 0:
            return (AHDL_MOVE(addr, offset),
                    AHDL_MOVE(we, AHDL_CONST(0)),
                    AHDL_MOVE(req, AHDL_CONST(1)))
        elif step == 1:
            return (AHDL_NOP('wait for output of {}'.format(self.acc_name)), )
        elif step == 2:
            if is_continuous:
                return (AHDL_MOVE(dst, q), )
            else:
                return (AHDL_MOVE(dst, q),
                        AHDL_MOVE(req, AHDL_CONST(0)))

    def write_sequence(self, step, offset, src, is_continuous):
        addr = port2ahdl(self, 'addr')
        we = port2ahdl(self, 'we')
        req = port2ahdl(self, 'req')
        d = port2ahdl(self, 'd')

        if step == 0:
            return (AHDL_MOVE(addr, offset),
                    AHDL_MOVE(we, AHDL_CONST(1)),
                    AHDL_MOVE(req, AHDL_CONST(1)),
                    AHDL_MOVE(d, src))
        elif step == 1:
            if is_continuous:
                return tuple()
            else:
                return (AHDL_MOVE(req, AHDL_CONST(0)), )


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
        self.ports = inf.ports.clone()

    def port_name(self, port):
        return '{}{}'.format(self.acc_name, port.name)

    def regs(self):
        return []

    def nets(self):
        return self.ports.all()

    def reset_stms(self):
        return []


def fifo_read_seq(inf, step, dst):
    empty = port2ahdl(inf, 'empty')
    read = port2ahdl(inf, 'read')
    dout = port2ahdl(inf, 'dout')

    if step == 0:
        ports = [empty]
        return (AHDL_META_WAIT('WAIT_VALUE', AHDL_CONST(0), *ports), )
    elif step == 1:
        return (AHDL_MOVE(read, AHDL_CONST(1)), )
    elif step == 2:
        return (AHDL_MOVE(read, AHDL_CONST(0)),
                AHDL_MOVE(dst, dout))


def fifo_write_seq(inf, step, src):
    full = port2ahdl(inf, 'full')
    write = port2ahdl(inf, 'write')
    din = port2ahdl(inf, 'din')

    if step == 0:
        ports = [full]
        return (AHDL_META_WAIT('WAIT_VALUE', AHDL_CONST(0), *ports), )
    elif step == 1:
        return (AHDL_MOVE(write, AHDL_CONST(1)),
                AHDL_MOVE(din, src))
    elif step == 2:
        return (AHDL_MOVE(write, AHDL_CONST(0)), )


class FIFOInterface(Interface):
    def __init__(self, signal):
        super().__init__(signal.name, '')
        self.signal = signal
        self.data_width = signal.width
        self.max_size = signal.maxsize

    def port_name(self, port):
        return self._port_name(port)

    def read_sequence(self, step, dst):
        return fifo_read_seq(self, step, dst)

    def write_sequence(self, step, src):
        return fifo_write_seq(self, step, src)

    def reset_stms(self):
        stms = []
        for p in self.ports.outports():
            stms.append(AHDL_MOVE(AHDL_SYMBOL(self.port_name(p)),
                                  AHDL_CONST(0)))
        return stms


class FIFOAccessor(IOAccessor):
    def __init__(self, inf, inst_name):
        super().__init__(inf, inst_name)

    def read_sequence(self, step, dst):
        return fifo_read_seq(self, step, dst)

    def write_sequence(self, step, src):
        return fifo_write_seq(self, step, src)

    def reset_stms(self):
        stms = []
        for p in self.ports.inports():
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
        self.ports = inf.ports.clone()

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
        ports = list(self.ports.outports())
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
        ports = list(self.ports.outports())
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
