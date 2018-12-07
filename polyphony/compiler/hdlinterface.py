from collections import namedtuple
from .ahdl import *
from .env import env


Port = namedtuple('Port', ('name', 'width', 'dir', 'signed'))


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
        return Ports([Port(p.name, p.width, flip(p.dir), p.signed) for p in self.ports])

    def renamed(self, rename_func):
        return Ports([Port(rename_func(p.name), p.width, p.dir, p.signed) for p in self.ports])

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
    if signal.is_valid_protocol() or signal.is_ready_valid_protocol():
        valid = port2ahdl(inf, 'valid')
        if signal.is_ready_valid_protocol():
            ready = port2ahdl(inf, 'ready')
            if step == 0:
                return (AHDL_MOVE(ready, AHDL_CONST(1)), )
            elif step == 1:
                expects = [(AHDL_CONST(1), valid)]
                return (AHDL_META_WAIT('WAIT_VALUE', *expects), )
            elif step == 2:
                if dst:
                    return (AHDL_MOVE(dst, data),
                            AHDL_MOVE(ready, AHDL_CONST(0)))
                else:
                    return (AHDL_MOVE(ready, AHDL_CONST(0)),)
        else:
            if step == 0:
                expects = [(AHDL_CONST(1), valid)]
                return (AHDL_META_WAIT('WAIT_VALUE', *expects), )
            elif step == 1:
                if dst:
                    return (AHDL_MOVE(dst, data), )
                else:
                    return tuple()
    else:
        if step == 0:
            if dst:
                return (AHDL_MOVE(dst, data), )
            else:
                return tuple()


def single_pipelined_read_seq(inf, signal, step, dst, stage):
    assert not signal.is_ready_valid_protocol()
    pipeline_state = stage.parent_state
    data = port2ahdl(inf, '')
    if step == 0:
        assert stage.has_enable
        if signal.is_valid_protocol():
            valid = port2ahdl(inf, 'valid')
            enable_cond = valid
        else:
            enable_cond = AHDL_CONST(1)
        enable_sig = pipeline_state.enable_signal(stage.step)
        if stage.enable:
            assert stage.enable.is_a(AHDL_MOVE)
            enable_cond = AHDL_OP('And', stage.enable.src, enable_cond)
        stage.enable = AHDL_MOVE(AHDL_VAR(enable_sig, Ctx.STORE), enable_cond)
        if dst:
            local_stms = (AHDL_MOVE(dst, data), )
        else:
            local_stms = tuple()
    else:
        local_stms = tuple()
    return local_stms, tuple()


def single_write_seq(inf, signal, step, src):
    data = port2ahdl(inf, '')
    if signal.is_valid_protocol() or signal.is_ready_valid_protocol():
        valid = port2ahdl(inf, 'valid')
        if signal.is_ready_valid_protocol():
            ready = port2ahdl(inf, 'ready')
            if step == 0:
                return (AHDL_MOVE(data, src),
                        AHDL_MOVE(valid, AHDL_CONST(1)))
            elif step == 1:
                expects = [(AHDL_CONST(1), ready)]
                return (AHDL_META_WAIT('WAIT_VALUE', *expects), )
            elif step == 2:
                return (AHDL_MOVE(valid, AHDL_CONST(0)), )
        else:
            if step == 0:
                return (AHDL_MOVE(data, src),
                        AHDL_MOVE(valid, AHDL_CONST(1)))
            elif step == 1:
                return (AHDL_MOVE(valid, AHDL_CONST(0)), )
    else:
        if step == 0:
            return (AHDL_MOVE(data, src), )


def single_pipelined_write_seq(inf, signal, step, src, stage):
    assert not signal.is_ready_valid_protocol()
    pipeline_state = stage.parent_state
    data = port2ahdl(inf, '')
    if step == 0:
        assert stage.has_enable
        if signal.is_valid_protocol():
            valid = port2ahdl(inf, 'valid')
            if stage.step == 0:
                pready = pipeline_state.ready_signal(0)
                valid_rhs = AHDL_VAR(pready, Ctx.LOAD)
            else:
                pvalid = pipeline_state.valid_signal(stage.step - 1)
                valid_rhs = AHDL_VAR(pvalid, Ctx.LOAD)
            local_stms = (AHDL_MOVE(data, src),)
            stage_stms = (AHDL_MOVE(valid, valid_rhs),)
        else:
            local_stms = (AHDL_MOVE(data, src), )
            stage_stms = tuple()
        enable_cond = AHDL_CONST(1)
        enable_sig = pipeline_state.enable_signal(stage.step)
        if stage.enable:
            assert stage.enable.is_a(AHDL_MOVE)
            enable_cond = AHDL_OP('And', stage.enable.src, enable_cond)
        stage.enable = AHDL_MOVE(AHDL_VAR(enable_sig, Ctx.STORE), enable_cond)
    else:
        local_stms = tuple()
        stage_stms = tuple()
    return local_stms, stage_stms


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

    def read_sequence(self, step, step_n, dst):
        return single_read_seq(self, self.signal, step, dst)


class PipelinedSingleReadInterface(SingleReadInterface):
    def accessor(self, inst_name=''):
        acc = PipelinedSingleWriteAccessor(self, inst_name)
        return acc

    def pipelined_read_sequence(self, step, step_n, dst, stage):
        if self.signal.is_ready_valid_protocol():
            assert self.signal.is_adaptered()
            bridge = PipelinedFIFOReadInterface(self.signal.adapter_sig)
            return bridge.pipelined_read_sequence(step, step_n, dst, stage)
        else:
            return single_pipelined_read_seq(self, self.signal, step, dst, stage)


class SingleWriteInterface(SinglePortInterface, WriteInterface):
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

    def write_sequence(self, step, step_n, src):
        return single_write_seq(self, self.signal, step, src)


class PipelinedSingleWriteInterface(SingleWriteInterface):
    def accessor(self, inst_name=''):
        acc = PipelinedSingleReadAccessor(self, inst_name)
        return acc

    def pipelined_write_sequence(self, step, step_n, src, stage):
        if self.signal.is_ready_valid_protocol():
            assert self.signal.is_adaptered()
            bridge = PipelinedFIFOWriteInterface(self.signal.adapter_sig)
            return bridge.pipelined_write_sequence(step, step_n, src, stage)
        else:
            return single_pipelined_write_seq(self, self.signal, step, src, stage)


class SinglePortAccessor(IOAccessor):
    def __init__(self, inf, inst_name):
        super().__init__(inf, inst_name)
        self.ports = inf.ports.clone()


class SingleReadAccessor(SinglePortAccessor):
    def reset_stms(self):
        stms = []
        signal = self.inf.signal

        if signal.is_ready_valid_protocol():
            ready = port2ahdl(self, 'ready')
            stms.append(AHDL_MOVE(ready, AHDL_CONST(0)))
        return stms

    def read_sequence(self, step, step_n, dst):
        return single_read_seq(self, self.inf.signal, step, dst)


class PipelinedSingleReadAccessor(SingleReadAccessor):
    def _adapter(self):
        adapter_inst_name = self.inst_name
        assert self.inf.signal.is_adaptered()
        adapter = PipelinedFIFOWriteInterface(self.inf.signal.adapter_sig).accessor(adapter_inst_name)
        return adapter

    def pipelined_read_sequence(self, step, step_n, dst, stage):
        if self.inf.signal.is_ready_valid_protocol():
            return self._adapter().pipelined_read_sequence(step, step_n, dst, stage)
        else:
            return single_pipelined_read_seq(self, self.inf.signal, step, dst, stage)


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
        if signal.is_valid_protocol() or signal.is_ready_valid_protocol():
            valid = port2ahdl(self, 'valid')
            stms.append(AHDL_MOVE(valid, AHDL_CONST(0)))
        return stms

    def write_sequence(self, step, step_n, src):
        return single_write_seq(self, self.inf.signal, step, src)


class PipelinedSingleWriteAccessor(SingleWriteAccessor):
    def _adapter(self):
        adapter_inst_name = self.inst_name
        assert self.inf.signal.is_adaptered()
        adapter = PipelinedFIFOReadInterface(self.inf.signal.adapter_sig).accessor(adapter_inst_name)
        return adapter

    def pipelined_write_sequence(self, step, step_n, src, stage):
        if self.inf.signal.is_ready_valid_protocol():
            return self._adapter().pipelined_write_sequence(step, step_n, src, stage)
        else:
            return single_pipelined_write_seq(self, self.inf.signal, step, src, stage)


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
            expects = [(AHDL_CONST(1), ready)]
            wait_ready = AHDL_META_WAIT("WAIT_VALUE", *expects)
            return (unset_valid, wait_ready)

    def callee_epilog(self, step, name):
        if step == 0:
            valid = port2ahdl(self, 'valid')
            accept = port2ahdl(self, 'accept')

            set_valid = AHDL_MOVE(valid, AHDL_CONST(1))
            expects = [(AHDL_CONST(1), accept)]
            wait_accept = AHDL_META_WAIT("WAIT_VALUE", *expects)
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

        if step == step_n - 3:
            expects = [(AHDL_CONST(1), valid)]
            seq.append(AHDL_META_WAIT('WAIT_VALUE', *expects))
        elif step == step_n - 2:
            for acc, ret in zip(retaccs, ahdl_call.returns):
                seq.extend(acc.read_sequence(0, step_n, ret))
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
        return Ports()

    def nets(self):
        return self.ports


class RAMBridgeInterface(Interface):
    def __init__(self, signal, name, owner_name, data_width, addr_width):
        super().__init__(name, owner_name)
        self.signal = signal
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
        return Ports()

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
        return Ports()

    def nets(self):
        return self.ports

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
            return Ports()

    def nets(self):
        if self.is_sink:
            return self.ports.outports()
        else:
            return self.ports

    def reset_stms(self):
        stms = []
        for p in self.ports.inports():
            stms.append(AHDL_MOVE(AHDL_SYMBOL(self.port_name(p)),
                                  AHDL_CONST(0)))
        return stms

    def pipelined(self, stage):
        return PipelinedRAMAccessor(self, stage)

    def read_sequence(self, step, step_n, offset, dst, is_continuous):
        assert step_n > 1
        addr = port2ahdl(self, 'addr')
        we = port2ahdl(self, 'we')
        req = port2ahdl(self, 'req')
        q = port2ahdl(self, 'q')

        if step == 0:
            return (AHDL_MOVE(addr, offset),
                    AHDL_MOVE(we, AHDL_CONST(0)),
                    AHDL_MOVE(req, AHDL_CONST(1)))
        elif step == step_n - 1:
            if is_continuous:
                if dst:
                    return (AHDL_MOVE(dst, q), )
                else:
                    return tuple()
            else:
                if dst:
                    return (AHDL_MOVE(dst, q),
                            AHDL_MOVE(req, AHDL_CONST(0)))
                else:
                    return (AHDL_MOVE(req, AHDL_CONST(0)), )
        else:
            return (AHDL_NOP('wait for output of {}'.format(self.acc_name)), )

    def write_sequence(self, step, step_n, offset, src, is_continuous):
        assert step_n > 1
        addr = port2ahdl(self, 'addr')
        we = port2ahdl(self, 'we')
        req = port2ahdl(self, 'req')
        d = port2ahdl(self, 'd')

        if step == 0:
            we_stm = AHDL_MOVE(we, AHDL_CONST(1))
            req_stm = AHDL_MOVE(req, AHDL_CONST(1))
            return (AHDL_MOVE(addr, offset),
                    we_stm,
                    req_stm,
                    AHDL_MOVE(d, src))
        elif step == 1:
            if is_continuous:
                return tuple()
            else:
                return (AHDL_MOVE(req, AHDL_CONST(0)), )
        else:
            return (AHDL_NOP('wait for input of {}'.format(self.acc_name)), )


class PipelinedRAMAccessor(RAMAccessor):
    def __init__(self, host, stage):
        assert isinstance(host, RAMAccessor)
        super().__init__(host.inf.signal, host.data_width, host.addr_width, host.is_sink)
        self.stage = stage
        self.pipeline_state = stage.parent_state

    def read_sequence(self, step, step_n, ahdl_load, is_continuous):
        assert step_n > 1
        assert ahdl_load.is_a(AHDL_LOAD)
        addr = port2ahdl(self, 'addr')
        req = port2ahdl(self, 'req')
        q = port2ahdl(self, 'q')
        offset = ahdl_load.offset
        dst = ahdl_load.dst
        if step == 0:
            req_valids = [AHDL_VAR(self.pipeline_state.ready_signal(0), Ctx.LOAD)]
            req_valids += [AHDL_VAR(self.pipeline_state.valid_signal(self.stage.step + i), Ctx.LOAD)
                           for i in range(step_n - 1)]
            req_rhs = AHDL_OP('BitOr', *req_valids)
            local_stms = (AHDL_MOVE(addr, offset),)
            stage_stms = tuple()
            self.pipeline_state.add_global_move(req.name,
                                                AHDL_MOVE(req, req_rhs))
        elif step == step_n - 1:
            if dst:
                local_stms = (AHDL_MOVE(dst, q), )
            else:
                local_stms = tuple()
            stage_stms = tuple()
        else:
            local_stms = (AHDL_NOP('wait for output of {}'.format(self.acc_name)), )
            stage_stms = tuple()

        return local_stms, stage_stms

    def write_sequence(self, step, step_n, ahdl_store, is_continuous):
        assert step_n > 1
        assert ahdl_store.is_a(AHDL_STORE)
        addr = port2ahdl(self, 'addr')
        we = port2ahdl(self, 'we')
        req = port2ahdl(self, 'req')
        d = port2ahdl(self, 'd')
        offset = ahdl_store.offset
        src = ahdl_store.src
        if step == 0:
            if self.stage.step == 0:
                pready = self.pipeline_state.ready_signal(0)
                valid_rhs = AHDL_VAR(pready, Ctx.LOAD)
            else:
                pvalid = self.pipeline_state.valid_signal(self.stage.step - 1)
                valid_rhs = AHDL_VAR(pvalid, Ctx.LOAD)
            local_stms = (AHDL_MOVE(addr, offset),
                          AHDL_MOVE(d, src),)
            stage_stms = tuple()
            we_conds = [
                valid_rhs,
                AHDL_OP('Eq',
                        AHDL_CONST(self.stage.state_idx),
                        AHDL_VAR(self.pipeline_state.substate_var, Ctx.LOAD))
            ]
            if ahdl_store.guard_cond:
                we_conds.append(ahdl_store.guard_cond)
            self.pipeline_state.add_global_move(we.name,
                                                AHDL_MOVE(we, AHDL_OP('And', *we_conds)))
            self.pipeline_state.add_global_move(req.name,
                                                AHDL_MOVE(req, valid_rhs))
        else:
            local_stms = tuple()
            stage_stms = tuple()
        return local_stms, stage_stms


class TupleInterface(Interface):
    def __init__(self, name, owner_name, data_width, length):
        super().__init__(name, owner_name)
        self.data_width = data_width
        self.length = length
        for i in range(length):
            pname = '{}'.format(i)
            self.ports.append(Port(pname, data_width, 'in', True))

    def accessor(self, inst_name=''):
        return TupleAccessor(self, inst_name)

    def port_name(self, port):
        return '{}_{}{}'.format(self.if_owner_name, self.if_name, port.name)

    def reset_stms(self):
        return []


class TupleAccessor(IOAccessor):
    def __init__(self, inf, inst_name):
        super().__init__(inf, inst_name)
        self.ports = inf.ports.clone()

    def port_name(self, port):
        return '{}{}'.format(self.acc_name, port.name)

    def regs(self):
        return Ports()

    def nets(self):
        return self.ports

    def reset_stms(self):
        return []


class RegArrayInterface(Interface):
    def __init__(self, signal, name, owner_name, data_width, length, direction, subscript):
        super().__init__(name, owner_name)
        self.signal = signal
        self.data_width = data_width
        self.length = length
        self.subscript = subscript
        for i in range(length):
            pname = '{}'.format(i)
            self.ports.append(Port(pname, data_width, direction, True))

    def accessor(self, inst_name=''):
        return RegArrayAccessor(self, inst_name)

    def port_name(self, port):
        if self.subscript:
            return '{}_{}[{}]'.format(self.if_owner_name, self.if_name, port.name)
        else:
            return '{}_{}{}'.format(self.if_owner_name, self.if_name, port.name)

    def reset_stms(self):
        return []

    def regs(self):
        return Ports()

    def nets(self):
        return self.ports


class RegArrayReadInterface(RegArrayInterface):
    def __init__(self, signal, name, owner_name, data_width, length, subscript=False):
        super().__init__(signal, name, owner_name, data_width, length, 'in', subscript)


class RegArrayWriteInterface(RegArrayInterface, WriteInterface):
    def __init__(self, signal, name, owner_name, data_width, length, subscript=False):
        super().__init__(signal, name, owner_name, data_width, length, 'out', subscript)


class RegArrayAccessor(IOAccessor):
    def __init__(self, inf, inst_name):
        super().__init__(inf, inst_name)
        self.ports = inf.ports.clone()

    def port_name(self, port):
        if self.inf.subscript:
            return '{}[{}]'.format(self.acc_name, port.name)
        else:
            return '{}{}'.format(self.acc_name, port.name)

    def regs(self):
        return Ports()

    def nets(self):
        return self.ports

    def reset_stms(self):
        return []

    def read_sequence(self, step, step_n, dst):
        assert dst.is_a(AHDL_MEMVAR)
        memnode = dst.memnode.single_source()
        mem_scope = memnode.scope
        hdlmodule = env.hdlmodule(mem_scope)
        sig = hdlmodule.signal(memnode.name())
        moves = []
        for i, p in enumerate(self.ports.outports()):
            src = AHDL_SYMBOL('{}{}'.format(self.acc_name, p.name))
            idst = AHDL_SUBSCRIPT(AHDL_MEMVAR(sig, memnode, Ctx.STORE), AHDL_CONST(i))
            mv = AHDL_MOVE(idst, src)
            moves.append(mv)
        return moves

    def write_sequence(self, step, step_n, src):
        assert src.is_a(AHDL_MEMVAR)


def fifo_read_seq(inf, step, dst):
    empty = port2ahdl(inf, 'empty')
    read = port2ahdl(inf, 'read')
    dout = port2ahdl(inf, 'dout')

    if step == 0:
        expects = [(AHDL_CONST(0), empty)]
        return (AHDL_META_WAIT('WAIT_VALUE', *expects), )
    elif step == 1:
        return (AHDL_MOVE(read, AHDL_CONST(1)), )
    elif step == 2:
        if dst:
            return (AHDL_MOVE(read, AHDL_CONST(0)),
                    AHDL_MOVE(dst, dout))
        else:
            return (AHDL_MOVE(read, AHDL_CONST(0)),)


def fifo_pipelined_read_seq(inf, step, dst, stage):
    empty = port2ahdl(inf, 'empty')
    will_empty = port2ahdl(inf, 'will_empty')
    read = port2ahdl(inf, 'read')
    dout = port2ahdl(inf, 'dout')
    pipeline_state = stage.parent_state
    if step == 0:
        assert stage.has_enable
        enable_sig = pipeline_state.enable_signal(stage.step)
        enable_cond = AHDL_OP('BitAnd',
                              AHDL_OP('Invert', empty),
                              AHDL_OP('Invert', will_empty))
        if stage.enable:
            assert stage.enable.is_a(AHDL_MOVE)
            enable_cond = AHDL_OP('And', stage.enable.src, enable_cond)
        stage.enable = AHDL_MOVE(AHDL_VAR(enable_sig, Ctx.STORE), enable_cond)

        read_rhs = pipeline_state.valid_exp(stage.step)
        local_stms = tuple()
        stage_stms = (AHDL_MOVE(read, read_rhs),
                     )
    elif step == 1:
        if dst:
            local_stms = (AHDL_MOVE(dst, dout), )
        else:
            local_stms = tuple()
        stage_stms = tuple()
    return local_stms, stage_stms


def fifo_write_seq(inf, step, src):
    full = port2ahdl(inf, 'full')
    write = port2ahdl(inf, 'write')
    din = port2ahdl(inf, 'din')

    if step == 0:
        expects = [(AHDL_CONST(0), full)]
        return (AHDL_META_WAIT('WAIT_VALUE', *expects), )
    elif step == 1:
        return (AHDL_MOVE(write, AHDL_CONST(1)),
                AHDL_MOVE(din, src))
    elif step == 2:
        return (AHDL_MOVE(write, AHDL_CONST(0)), )


def fifo_pipelined_write_seq(inf, step, src, stage):
    full = port2ahdl(inf, 'full')
    will_full = port2ahdl(inf, 'will_full')
    write = port2ahdl(inf, 'write')
    din = port2ahdl(inf, 'din')
    pipeline_state = stage.parent_state
    if step == 0:
        assert stage.has_enable
        enable_sig = pipeline_state.enable_signal(stage.step)
        enable_cond = AHDL_OP('BitAnd',
                              AHDL_OP('Invert', full),
                              AHDL_OP('Invert', will_full),
                              )
        if stage.enable:
            assert stage.enable.is_a(AHDL_MOVE)
            enable_cond = AHDL_OP('And', stage.enable.src, enable_cond)
        stage.enable = AHDL_MOVE(AHDL_VAR(enable_sig, Ctx.STORE), enable_cond)
        write_rhs = pipeline_state.valid_exp(stage.step)
        local_stms = (AHDL_MOVE(din, src), )
        stage_stms = (AHDL_MOVE(write, write_rhs),
                     )
    return local_stms, stage_stms


class FIFOInterface(Interface):
    def __init__(self, signal):
        super().__init__(signal.name, '')
        self.signal = signal
        self.data_width = signal.width
        self.max_size = signal.maxsize

    def port_name(self, port):
        return self._port_name(port)

    def read_sequence(self, step, step_n, dst):
        return fifo_read_seq(self, step, dst)

    def write_sequence(self, step, step_n, src):
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

    def read_sequence(self, step, step_n, dst):
        return fifo_read_seq(self, step, dst)

    def write_sequence(self, step, step_n, src):
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
        self.ports.append(Port('will_full', 1, 'out', False))
        self.ports.append(Port('will_empty', 1, 'out', False))

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
        self.ports.append(Port('will_empty', 1, 'in', False))

    def accessor(self, inst_name=''):
        return FIFOWriteAccessor(self, inst_name)


class PipelinedFIFOReadInterface(FIFOReadInterface):
    def __init__(self, signal):
        super().__init__(signal)

    def accessor(self, inst_name=''):
        return PipelinedFIFOWriteAccessor(self, inst_name)

    def pipelined_read_sequence(self, step, step_n, dst, stage):
        return fifo_pipelined_read_seq(self, step, dst, stage)


class FIFOWriteInterface(FIFOInterface, WriteInterface):
    def __init__(self, signal):
        super().__init__(signal)
        self.ports.append(Port('din', self.data_width, 'out', True))
        self.ports.append(Port('write', 1, 'out', False))
        self.ports.append(Port('full', 1, 'in', False))
        self.ports.append(Port('will_full', 1, 'in', False))

    def accessor(self, inst_name=''):
        return FIFOReadAccessor(self, inst_name)


class PipelinedFIFOWriteInterface(FIFOWriteInterface):
    def __init__(self, signal):
        super().__init__(signal)

    def accessor(self, inst_name=''):
        return PipelinedFIFOReadAccessor(self, inst_name)

    def pipelined_write_sequence(self, step, step_n, src, stage):
        return fifo_pipelined_write_seq(self, step, src, stage)


class FIFOReadAccessor(FIFOAccessor):
    def __init__(self, inf, inst_name):
        super().__init__(inf, inst_name)
        data_width = self.inf.data_width
        # reading ports for fifo module interface
        self.ports.append(Port('dout', data_width, 'out', True))
        self.ports.append(Port('read', 1, 'in', False))
        self.ports.append(Port('empty', 1, 'out', False))
        self.ports.append(Port('will_empty', 1, 'out', False))

    def nets(self):
        ports = self.ports.outports()
        # nets for fifo write interface
        ports.append(Port('din', self.inf.data_width, 'out', True))
        ports.append(Port('write', 1, 'out', False))
        ports.append(Port('full', 1, 'out', False))
        ports.append(Port('will_full', 1, 'out', False))
        return ports


class PipelinedFIFOReadAccessor(FIFOReadAccessor):
    def __init__(self, inf, inst_name):
        super().__init__(inf, inst_name)

    def pipelined_read_sequence(self, step, step_n, dst, stage):
        return fifo_pipelined_read_seq(self, step, dst, stage)


class FIFOWriteAccessor(FIFOAccessor):
    def __init__(self, inf, inst_name):
        super().__init__(inf, inst_name)
        data_width = self.inf.data_width
        # writingg ports for fifo module interface
        self.ports.append(Port('din', data_width, 'in', True))
        self.ports.append(Port('write', 1, 'in', False))
        self.ports.append(Port('full', 1, 'out', False))
        self.ports.append(Port('will_full', 1, 'out', False))
        # nets for fifo write interface

    def nets(self):
        ports = self.ports.outports()
        # nets for fifo write interface
        ports.append(Port('dout', self.inf.data_width, 'out', True))
        ports.append(Port('read', 1, 'out', False))
        ports.append(Port('empty', 1, 'out', False))
        ports.append(Port('will_empty', 1, 'out', False))
        return ports


class PipelinedFIFOWriteAccessor(FIFOWriteAccessor):
    def __init__(self, inf, inst_name):
        super().__init__(inf, inst_name)

    def pipelined_write_sequence(self, step, step_n, dst, stage):
        return fifo_pipelined_write_seq(self, step, dst, stage)


def create_local_accessor(signal):
    assert not signal.is_input() and not signal.is_output()
    if signal.is_single_port():
        if signal.is_pipelined_port():
            reader = PipelinedSingleWriteInterface(signal).accessor('')
            writer = PipelinedSingleReadInterface(signal).accessor('')
        else:
            reader = SingleWriteInterface(signal).accessor('')
            writer = SingleReadInterface(signal).accessor('')
    elif signal.is_fifo_port():
        if signal.is_pipelined_port():
            reader = PipelinedFIFOWriteInterface(signal).accessor('')
            writer = PipelinedFIFOReadInterface(signal).accessor('')
        else:
            reader = FIFOWriteInterface(signal).accessor('')
            writer = FIFOReadInterface(signal).accessor('')
    return reader, writer


def create_single_port_interface(signal):
    inf = None
    if signal.is_input():
        if signal.is_pipelined_port():
            inf = PipelinedSingleReadInterface(signal)
        else:
            inf = SingleReadInterface(signal)
    elif signal.is_output():
        if signal.is_pipelined_port():
            inf = PipelinedSingleWriteInterface(signal)
        else:
            inf = SingleWriteInterface(signal)
    return inf


def create_seq_interface(signal):
    inf = None
    if signal.is_fifo_port():
        if signal.is_input():
            if signal.is_pipelined_port():
                inf = PipelinedFIFOReadInterface(signal)
            else:
                inf = FIFOReadInterface(signal)
        elif signal.is_output():
            if signal.is_pipelined_port():
                inf = PipelinedFIFOWriteInterface(signal)
            else:
                inf = FIFOWriteInterface(signal)
    return inf


def make_event_task(hdlmodule, reset_stms, stms):
    clk = hdlmodule.gen_sig('clk', 1, {'reserved'})
    rst = hdlmodule.gen_sig('rst', 1, {'reserved'})
    blocks = [AHDL_BLOCK('', reset_stms), AHDL_BLOCK('', stms)]
    reset_if = AHDL_IF([AHDL_VAR(rst, Ctx.LOAD), AHDL_CONST(1)], blocks)
    events = [(AHDL_VAR(clk, Ctx.LOAD), 'rising')]
    return AHDL_EVENT_TASK(events, reset_if)


def single_input_port_fifo_adapter(hdlmodule, signal, inst_name=''):
    '''
    if (rst) begin
      port_ready <= 0;
      fifo_write <= 0;
      fifo_din <= 0;
    end else begin
      port_ready <= ~fifo_full;
      fifo_write <= port_valid & ~fifo_full;
      fifo_din <= port;
    end
    '''
    assert signal.is_ready_valid_protocol()
    if inst_name:
        #assert signal.is_outputput()
        port_name = '{}_{}'.format(inst_name, signal.name)
        fifo_name = '{}_{}'.format(inst_name, signal.adapter_sig.name)
    else:
        assert signal.is_input()
        port_name = signal.name
        fifo_name = signal.adapter_sig.name
    port = AHDL_SYMBOL(port_name)
    port_valid = AHDL_SYMBOL(port_name + '_valid')
    port_ready = AHDL_SYMBOL(port_name + '_ready')
    fifo_write = AHDL_SYMBOL(fifo_name + '_write')
    fifo_full = AHDL_SYMBOL(fifo_name + '_full')
    fifo_din = AHDL_SYMBOL(fifo_name + '_din')
    reset_stms = [AHDL_MOVE(port_ready, AHDL_CONST(0)),
                  AHDL_MOVE(fifo_write, AHDL_CONST(0)),
                  AHDL_MOVE(fifo_din, AHDL_CONST(0)),
                  ]
    stms = [AHDL_MOVE(port_ready, AHDL_OP('Invert', fifo_full)),
            AHDL_MOVE(fifo_write, AHDL_OP('BitAnd', port_valid, AHDL_OP('Invert', fifo_full))),
            AHDL_MOVE(fifo_din, port)
            ]
    return make_event_task(hdlmodule, reset_stms, stms)


def single_output_port_fifo_adapter(hdlmodule, signal, inst_name=''):
    '''
    if (rst) begin
      port <= 0;
      port_valid <= 0;
      fifo_read <= 0;
    end else begin
      fifo_read <= (~fifo_empty & port_ready) ? 1 : 0;
      port_valid <= fifo_read;
      port <= fifo_read ? fifo_dout : port;
    end
    '''
    assert signal.is_ready_valid_protocol()
    if inst_name:
        #assert signal.is_input()
        port_name = '{}_{}'.format(inst_name, signal.name)
        fifo_name = '{}_{}'.format(inst_name, signal.adapter_sig.name)
    else:
        assert signal.is_output()
        port_name = signal.name
        fifo_name = signal.adapter_sig.name
    port = AHDL_SYMBOL(port_name)
    port_valid = AHDL_SYMBOL(port_name + '_valid')
    port_ready = AHDL_SYMBOL(port_name + '_ready')
    fifo_read = AHDL_SYMBOL(fifo_name + '_read')
    fifo_empty = AHDL_SYMBOL(fifo_name + '_empty')
    fifo_dout = AHDL_SYMBOL(fifo_name + '_dout')
    reset_stms = [AHDL_MOVE(port, AHDL_CONST(0)),
                  AHDL_MOVE(port_valid, AHDL_CONST(0)),
                  AHDL_MOVE(fifo_read, AHDL_CONST(0)),
                  ]
    fifo_read_rhs = AHDL_IF_EXP(AHDL_OP('BitAnd',
                                        AHDL_OP('Invert', fifo_empty),
                                        port_ready),
                                AHDL_CONST(1),
                                AHDL_CONST(0))
    port_rhs = AHDL_IF_EXP(fifo_read,
                           fifo_dout,
                           port)
    stms = [AHDL_MOVE(fifo_read, fifo_read_rhs),
            AHDL_MOVE(port_valid, fifo_read),
            AHDL_MOVE(port, port_rhs),
            ]
    return make_event_task(hdlmodule, reset_stms, stms)


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

