from polyphony import module, Reg
from polyphony.io import Port, flipped
from polyphony.timing import timed, clkfence, clksleep, wait_value

@timed
@inlinelib
@module
class Handshake:
    def __init__(self, dtype, direction, init=None):
        self.data = Port(dtype, direction, init)
        if direction == 'in':
            self.ready = Port(bool, 'out', 0, rewritable=True)
            self.valid = Port(bool, 'in', rewritable=True)
        else:
            self.ready = Port(bool, 'in', rewritable=True)
            self.valid = Port(bool, 'out', 0, rewritable=True)

    def rd(self):
        '''
        Read the current value from the port.
        '''
        self.ready.wr(True)
        clkfence()
        wait_value(True, self.valid)
        self.ready.wr(False)
        return self.data.rd()

    def wr(self, v):
        '''
        Write the value to the port.
        '''
        self.data.wr(v)
        self.valid.wr(True)
        clkfence()
        wait_value(True, self.ready)
        self.valid.wr(False)



@timed
@inlinelib
@module
class RAMPort:
    def __init__(self, dtype, delay):
        self.data = Port(dtype, 'out')
        self.addr = Port(int,   'out')
        self.we   = Port(bool,  'out', rewritable=True)
        self.q    = Port(dtype, 'in', 0)
        #self.delay = delay

    def rd(self, addr):
        self.addr.wr(addr)
        #clksleep(self.delay)
        clksleep(2)
        return self.q.rd()

    def wr(self, addr, data):
        self.addr.wr(addr)
        self.we.wr(True)
        self.data.wr(data)
        clkfence()
        self.we.wr(False)


@timed
@module
@inlinelib
class RAMModule:
    def __init__(self, dtype, capacity, delay):
        self.port = flipped(RAMPort(dtype, delay))
        self.mem = [0] * capacity
        self.append_worker(self.main, loop=True)
        self.addr_latch = 0
        self.port.q.assign(lambda:self.mem[self.addr_latch])

    def main(self):
        if self.port.we.rd():
            self.mem[self.port.addr.rd()] = self.port.data.rd()
        self.addr_latch = self.port.addr.rd()


@timed
@inlinelib
@module
class FIFOPort:
    def __init__(self, dtype, direction):
        if direction == 'in':
            self.dout = Port(dtype, 'in')
            self.empty = Port(bool, 'in')
            self.read = Port(bool, 'out', False, rewritable=True)
        else:
            self.din = Port(dtype, 'out', 0)
            self.full = Port(bool, 'in')
            self.write = Port(bool, 'out', False, rewritable=True)

    def rd(self):
        wait_value(False, self.empty)
        self.read.wr(True)
        clkfence()
        self.read.wr(False)
        v = Reg()
        v.v = self.dout.rd()
        clkfence()
        return v.v

    def wr(self, v):
        wait_value(False, self.full)
        self.write.wr(True)
        self.din.wr(v)
        clkfence()
        self.write.wr(False)


@timed
@module
@inlinelib
class FIFOModule:
    def __init__(self, dtype, capacity):
        self.reader = flipped(FIFOPort(dtype, 'in'))
        self.writer = flipped(FIFOPort(dtype, 'out'))
        self.append_worker(self.worker, loop=True)
        self.append_worker(self.update_flag, loop=True)
        self.length = capacity

        self.mem = [0] * capacity
        self.wp = 0
        self.rp = 0
        self._empty = 1
        self._full = 0

        self.reader.empty.assign(lambda:self._empty == 1)
        self.reader.dout.assign(lambda:self.mem[self.rp])
        self.writer.full.assign(lambda:self._full == 1)

    def inc_rp(self):
        self.rp = 0 if self.rp == (self.length - 1) else self.rp + 1

    def inc_wp(self):
        self.wp = 0 if self.wp == (self.length - 1) else self.wp + 1

    def worker(self):
        if self.reader.read.rd() and not self._empty:
            self.inc_rp()
        if self.writer.write.rd() and not self._full:
            self.inc_wp()
            self.mem[self.wp] = self.writer.din.rd()

    def update_flag(self):
        if (self.writer.write.rd()
                and not self._full
                and self.wp + 1 == self.rp):
            self._full = 1
        elif self._full and self.wp == self.rp:
            self._full = 1
        else:
            self._full = 0
        if (self.reader.read.rd()
                and not self._empty
                and self.rp + 1 == self.wp):
            self._empty = 1
        elif self._empty and self.wp == self.rp:
            self._empty = 1
        else:
            self._empty = 0
