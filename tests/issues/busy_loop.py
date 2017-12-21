from polyphony import module, testbench, is_worker_running
from polyphony.io import Queue


@module
class busy_loop:
    def __init__(self):
        self.i = Queue(int, 'in')
        self.append_worker(self.w)

    def w(self):
        while is_worker_running():
            while True:
                d = self.i.rd()
                assert d == 0
                d = self.i.rd()
                assert d == 1
                d = self.i.rd()
                assert d == 2
            while True:
                d = self.i.rd()


@testbench
def test(m):
    m.i.wr(0)
    m.i.wr(1)
    m.i.wr(2)


m = busy_loop()
test(m)
