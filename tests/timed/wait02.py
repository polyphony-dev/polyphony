from polyphony import module, testbench, Reg
from polyphony.timing import timed, clkfence, clktime, wait_value
from polyphony.io import Port


@module
class wait02:
    def __init__(self):
        self.start = Port(bool, 'in')
        self.flag1 = Port(bool, 'in')
        self.flag2 = Port(bool, 'in')
        self.flag3 = Port(bool, 'in')
        self.o = Port(int, 'out', -1)
        self.t1 = Reg()
        self.t2 = Reg()
        self.append_worker(self.untimed_worker, loop=True)

    @timed
    def timed_func(self):
        wait_value(True, self.start)

        self.t1.v = clktime()
        wait_value(True, self.flag1)
        wait_value(True, self.flag2)
        wait_value(True, self.flag3)
        self.t2.v = clktime()

        clkfence()
        print(self.t1.v, self.t2.v)
        self.o.wr(self.t2.v - self.t1.v)
        #self.o.wr(1)

    def untimed_worker(self):
        self.timed_func()


@testbench
@timed
def test(m):
    m.flag1.wr(True)
    m.flag2.wr(True)
    m.flag3.wr(True)
    m.start.wr(True)
    clkfence()

    m.start.wr(False)
    clkfence()
    clkfence()

    assert 0 == m.o.rd()
    m.flag1.wr(False)
    m.flag2.wr(False)
    m.flag3.wr(False)
    clkfence()

    m.start.wr(True)
    clkfence()
    m.start.wr(False)
    m.flag1.wr(True)
    clkfence()
    m.flag2.wr(True)
    clkfence()
    clkfence()
    m.flag3.wr(True)
    clkfence()
    clkfence()
    clkfence()
    assert 4 == m.o.rd()


m = wait02()
test(m)
