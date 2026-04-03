from polyphony import module
from polyphony import testbench
from polyphony import is_worker_running
from polyphony.io import Port
from polyphony.typing import int8, int16
from polyphony.timing import clksleep, wait_value


@module
class ParamSub:
    def __init__(self, scale, offset):
        self.i = Port(int16, 'in')
        self.o = Port(int16, 'out')
        self.scale = scale
        self.offset = offset
        self.append_worker(self.run)

    def run(self):
        while is_worker_running():
            self.o.wr(self.i.rd() * self.scale + self.offset)


@module
class Nesting06:
    def __init__(self):
        self.sub_a = ParamSub(3, 1)
        self.sub_b = ParamSub(2, 5)
        self.start = Port(bool, 'in', init=False)
        self.result = Port(int16, 'out')
        self.append_worker(self.worker)

    def worker(self):
        wait_value(True, self.start)
        self.sub_a.i.wr(10)
        self.sub_b.i.wr(10)
        clksleep(5)
        # sub_a: 10 * 3 + 1 = 31
        # sub_b: 10 * 2 + 5 = 25
        total = self.sub_a.o.rd() + self.sub_b.o.rd()
        self.result.wr(total)


@testbench
def test():
    m = Nesting06()
    m.start.wr(True)
    clksleep(20)
    # 31 + 25 = 56
    assert m.result.rd() == 56
