from collections import namedtuple
from .ahdl import *


Port = namedtuple('Port', ('name', 'width', 'dir', 'signed', 'default'))


class Ports(object):
    def __init__(self, ports=None):
        if ports:
            self.ports = ports
        else:
            self.ports = []

    def __str__(self):
        return ', '.join(['<{}:{}:{}>'.format(p.name, p.width, p.dir)
                          for p in self.ports])

    def __getitem__(self, key):
        for p in self.ports:
            if p.name == key:
                return p
        raise IndexError()

    def __contains__(self, key):
        return key in [p.name for p in self.ports]

    def __iter__(self):
        self.i = 0
        return self

    def __next__(self):
        if self.i < len(self.ports):
            p = self.ports[self.i]
            self.i += 1
            return p
        else:
            raise StopIteration

    def __add__(self, other):
        return Ports(self.ports + other.ports)

    def append(self, port):
        self.ports.append(port)

    def flipped(self):
        def flip(d):
            return 'in' if d == 'out' else 'out'
        return Ports([Port(p.name, p.width, flip(p.dir), p.signed, p.default) for p in self.ports])

    def renamed(self, rename_func):
        return Ports([Port(rename_func(p.name), p.width, p.dir, p.signed, p.default) for p in self.ports])

    def inports(self):
        return Ports([p for p in self.ports if p.dir == 'in'])

    def outports(self):
        return Ports([p for p in self.ports if p.dir == 'out'])

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


class WriteInterface(object):
    pass


class Accessor(object):
    def __init__(self, inf):
        self.acc_name = inf.if_name
        self.inf = inf
        self.ports = Ports()
        self.connected = True

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

    def is_internal(self):
        return True if self.inst_name else False


def single_read_seq(inf, signal, step, dst):
    # blocking if the port is not 'valid'
    data = port2ahdl(inf, '')
    if step == 0:
        if dst:
            return (AHDL_MOVE(dst, data), )
        else:
            return tuple()


def single_write_seq(inf, signal, step, src):
    data = port2ahdl(inf, '')
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
        self.ports.append(Port('', self.data_width, 'in', signed, signal.init_value))

    def accessor(self, inst_name=''):
        acc = SingleWriteAccessor(self, inst_name)
        return acc

    def reset_stms(self):
        return []

    def read_sequence(self, step, step_n, dst):
        return single_read_seq(self, self.signal, step, dst)


class SingleWriteInterface(SinglePortInterface, WriteInterface):
    def __init__(self, signal, if_name='', if_owner_name=''):
        if if_name:
            super().__init__(signal, if_name, if_owner_name)
        else:
            super().__init__(signal, signal.name, if_owner_name)
        #assert signal.is_output()
        signed = True if signal.is_int() else False
        self.ports.append(Port('', self.data_width, 'out', signed, signal.init_value))

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
        return stms

    def write_sequence(self, step, step_n, src):
        return single_write_seq(self, self.signal, step, src)


class SinglePortAccessor(IOAccessor):
    def __init__(self, inf, inst_name):
        super().__init__(inf, inst_name)
        self.ports = inf.ports.clone()


class SingleReadAccessor(SinglePortAccessor):
    def reset_stms(self):
        return []

    def read_sequence(self, step, step_n, dst):
        return single_read_seq(self, self.inf.signal, step, dst)


class SingleWriteAccessor(SinglePortAccessor):
    def reset_stms(self):
        stms = []
        signal = self.inf.signal
        if hasattr(signal, 'init_value'):
            iv = signal.init_value
        else:
            iv = 0
        stms.append(AHDL_MOVE(AHDL_SYMBOL(self.acc_name),
                              AHDL_CONST(iv)))
        return stms

    def write_sequence(self, step, step_n, src):
        return single_write_seq(self, self.inf.signal, step, src)


class CallInterface(Interface):
    def __init__(self, name, owner_name=''):
        super().__init__(name, owner_name)
        self.ports.append(Port('ready', 1, 'in', False, 0))
        self.ports.append(Port('accept', 1, 'in', False, 0))
        self.ports.append(Port('valid', 1, 'out', False, 0))

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
            args = ['Eq', AHDL_CONST(1), ready]
            wait_ready = AHDL_META_WAIT("WAIT_COND", *args)
            return (unset_valid, wait_ready)

    def callee_epilog(self, step, name):
        if step == 0:
            valid = port2ahdl(self, 'valid')
            accept = port2ahdl(self, 'accept')

            set_valid = AHDL_MOVE(valid, AHDL_CONST(1))
            args = ['Eq', AHDL_CONST(1), accept]
            wait_accept = AHDL_META_WAIT("WAIT_COND", *args)
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

    def call_sequence(self, step, step_n, argaccs, retaccs, ahdl_call):
        seq = []
        valid = port2ahdl(self, 'valid')
        ready = port2ahdl(self, 'ready')
        accept = port2ahdl(self, 'accept')

        if step == 0:
            seq = [AHDL_MOVE(ready, AHDL_CONST(1))]
            for acc, arg in zip(argaccs, ahdl_call.args):
                if arg.is_a(AHDL_MEMVAR):
                    continue
                seq.extend(acc.write_sequence(0, step_n, arg))
        elif step == 1:
            seq = [AHDL_MOVE(ready, AHDL_CONST(0))]
            args = ['Eq', AHDL_CONST(1), valid]
            seq.append(AHDL_META_WAIT('WAIT_COND', *args))
            for acc, ret in zip(retaccs, ahdl_call.returns):
                seq.extend(acc.read_sequence(0, step_n, ret))
            seq.append(AHDL_MOVE(accept, AHDL_CONST(1)))
        elif step == 2:
            seq.append(AHDL_MOVE(accept, AHDL_CONST(0)))
        return tuple(seq)
