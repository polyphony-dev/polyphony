from polyphony import module
from polyphony import testbench
from polyphony.timing import wait_value
from polyphony.io import Bit


class Interface:
    def __init__(self):
        self.i0 = Bit()
        self.i1 = Bit()
        self.o0 = Bit()
        self.o1 = Bit()


@module
class WorkerTest04:
    def __init__(self):
        self.inf = Interface()
        self.append_worker(self.worker, 'foo', self.inf.i0, self.inf.o0)
        self.append_worker(self.worker, 'bar', self.inf.i1, self.inf.o1)

    def worker(self, name, i, o):
        wait_value(1, i)
        print('worker', name, i.rd())
        o.wr(1)


@testbench
def test(wtest):
    wtest.inf.i0.wr(1)
    wait_value(1, wtest.inf.o0)
    assert wtest.inf.o0.rd() == 1

    wtest.inf.i1.wr(1)
    wait_value(1, wtest.inf.o1)
    assert wtest.inf.o1.rd() == 1


w = WorkerTest04()
test(w)
