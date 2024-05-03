from polyphony import testbench
from polyphony import module
from polyphony.io import Port
from polyphony.timing import timed, clkrange, clkfence


@timed
@module
class tuple_field01:
    def __init__(self, v):
        self.in0 = Port(int, 'in')
        self.out0 = Port(int, 'out')
        # self.out0.assign(self.worker)
        self.mem = (v + 1, v + 2, v + 3, v + 4)
        self.append_worker(self.worker, loop=True)

    def worker(self):
        i = self.in0.rd()
        v = self.mem[i]
        self.out0.wr(v)

    def f(self):
        i = self.in0.rd()
        v = self.mem[i]
        return v

@timed
@testbench
def test():
    t = tuple_field01(1)
    indices = (3, 2, 1, 0, 1, 2, 3)
    v = 1
    expects = (v+4, v+3, v+2, v+1, v+2, v+3, v+4)
    for i in clkrange(len(indices)):
        v = indices[i]
        # print('idx', i, v)
        t.in0.wr(v)
        clkfence()
        clkfence()
        o = t.out0.rd()
        assert expects[i] == o
        print(o)
