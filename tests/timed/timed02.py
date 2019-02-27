from polyphony import module, rule
from polyphony import testbench
from polyphony.io import Port
from polyphony.timing import clkfence, wait_value


class Handshake:
    def __init__(self, dtype, direction, init=None):
        self.data = Port(dtype, direction, init)
        if direction == 'in':
            self.ready = Port(bool, 'out', 0)
            self.valid = Port(bool, 'in')
        else:
            self.ready = Port(bool, 'in')
            self.valid = Port(bool, 'out', 0)

    def rd(self):
        '''
        Read the current value from the port.
        '''
        self.ready.wr(True)
        clkfence()
        while self.valid.rd() is not True:
            clkfence()
        #wait_value(True, self.valid)
        self.ready.wr(False)
        return self.data.rd()

    def wr(self, v):
        '''
        Write the value to the port.
        '''
        self.data.wr(v)
        self.valid.wr(True)
        clkfence()
        if self.ready.rd() is not True:
            clkfence()
        #wait_value(True, self.ready)
        self.valid.wr(False)


@module
class timed02:
    def __init__(self):
        self.i = Handshake(int, 'in')
        self.o = Handshake(int, 'out')
        self.append_worker(self.w)

    @rule(scheduling='timed')
    def w(self):
        x = self.i.rd()
        clkfence()
        # 2
        print(x)
        clkfence()
        # 3
        self.o.wr(10)
        clkfence()
        # 4
        clkfence()
        # 5
        self.o.wr(20)
        clkfence()
        # 6
        clkfence()


@rule(scheduling='timed')
@testbench
def test(m):
    #0
    m.i.wr(3)
    clkfence()
    # 1
    clkfence()
    # 2
    clkfence()
    # 3
    print(m.o.rd())
    clkfence()
    # 4
    print(m.o.rd())
    clkfence()
    # 5
    clkfence()
    # 6
    clkfence()


m = timed02()
test(m)
