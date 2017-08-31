from polyphony import testbench, module, is_worker_running, rule
from polyphony.io import Port
from polyphony.typing import int8
from polyphony.timing import clkfence


@module
class Protocol04:
    def __init__(self):
        self.i1 = Port(int8, 'in', init=0, protocol='valid')
        self.i2 = Port(int8, 'in', init=0, protocol='valid')
        self.i3 = Port(int8, 'in', init=0, protocol='valid')
        self.o1 = Port(int8, 'out', init=0, protocol='valid')
        self.o2 = Port(int8, 'out', init=0, protocol='valid')
        self.o3 = Port(int8, 'out', init=0, protocol='valid')
        self.append_worker(self.main)

    def main(self):
        while is_worker_running():
            with rule(scheduling='parallel'):
                t1 = self.i1.rd()
                t2 = self.i2.rd()
                t3 = self.i3.rd()
                self.o1.wr(t1 * t1)
                self.o2.wr(t2 * t2)
                self.o3.wr(t3 * t3)


@testbench
def test(p04):
    with rule(scheduling='parallel'):
        p04.i1.wr(2)
        p04.i2.wr(3)
        p04.i3.wr(4)
        clkfence()
        assert p04.o1() == 4
        assert p04.o2() == 9
        assert p04.o3() == 16


p04 = Protocol04()
test(p04)
