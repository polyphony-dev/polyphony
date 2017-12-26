#Port direction of 'p' is conflicted
from polyphony import testbench
from polyphony import module
from polyphony.io import Queue


@module
class io_conflict02:
    def __init__(self):
        self.p = Queue(int, 'in')
        self.append_worker(self.w)

    def w(self):
        data = self.p.rd()
        print(data)


m = io_conflict02()


@testbench
def test(m):
    v = m.p.rd()


test(m)
