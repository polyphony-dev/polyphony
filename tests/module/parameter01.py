from polyphony import module
from polyphony import testbench
from polyphony.io import Queue
from polyphony.typing import uint8

@module
class parameter01:
    def __init__(self, PARAM0, PARAM1:uint8=2):
        self.p0 = PARAM0
        self.p1 = PARAM0 + PARAM1
        self.o0 = Queue(int, 'out')
        self.o1 = Queue(int, 'out')
        self.append_worker(self.w)

    def w(self):
        self.o0.wr(self.p0)
        self.o1.wr(self.p1)


@testbench
def test0(m):
    assert 10 == m.o0.rd()
    assert 12 == m.o1.rd()


m0 = parameter01(10)
test0(m0)


@testbench
def test1(m):
    assert 1 == m.o0.rd()
    assert 17 == m.o1.rd()


m1 = parameter01(1, 16)
test1(m1)
