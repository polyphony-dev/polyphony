from polyphony import testbench, module, is_worker_running
from polyphony.io import Queue
from polyphony.typing import int8


@module
class queue04:
    def __init__(self):
        self.in_q = Queue(int8, 'in', maxsize=2)
        self.out_q = Queue(int8, 'out', maxsize=2)
        self.tmp_q = Queue(int8, 'any', maxsize=2)
        self.append_worker(self.worker1)
        self.append_worker(self.worker2)

    def worker1(self):
        while is_worker_running():
            d = self.in_q.rd()
            self.tmp_q.wr(d)

    def worker2(self):
        while is_worker_running():
            d = self.tmp_q.rd()
            self.out_q.wr(d)


@testbench
def test(q):
    q.in_q.wr(1)
    q.in_q.wr(2)
    q.in_q.wr(3)
    q.in_q.wr(4)
    #q.tmp_q.wr(4)
    assert 1 == q.out_q.rd()
    assert 2 == q.out_q.rd()
    assert 3 == q.out_q.rd()
    assert 4 == q.out_q.rd()


q = queue04()
test(q)
