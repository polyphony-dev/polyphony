from polyphony import testbench, module, is_worker_running
from polyphony.io import Queue
from polyphony.typing import int8


@module
class queue03:
    def __init__(self):
        self.in_q = Queue(int8, 'in', maxsize=2)
        self.out1_q = Queue(int8, 'out', maxsize=2)
        self.out2_q = Queue(int8, 'out', maxsize=2)
        self.append_worker(self.main, self.in_q, self.out1_q, self.out2_q)

    def main(self, in_q, out1_q, out2_q):
        while is_worker_running():
            d = in_q.rd()
            if d == 0:
                out1_q.wr(d)
            else:
                out2_q.wr(d)


@testbench
def test(q):
    q.in_q.wr(0)
    q.in_q.wr(1)
    q.in_q.wr(0)
    q.in_q.wr(2)
    assert 0 == q.out1_q.rd()
    assert 0 == q.out1_q.rd()
    assert 1 == q.out2_q.rd()
    assert 2 == q.out2_q.rd()


q = queue03()
test(q)
