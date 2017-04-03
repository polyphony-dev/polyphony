from polyphony import testbench, module, is_worker_running
from polyphony.io import Queue
from polyphony.typing import int8

@module
class Port04:
    def __init__(self):
        self.in_q = Queue(int8, maxsize=2)
        self.out_q = Queue(int8, maxsize=2)
        tmp_q = Queue(int8, maxsize=2)
        self.append_worker(self.main, self.in_q, tmp_q)
        self.append_worker(self.main, tmp_q, self.out_q)

    def main(self, in_q, out_q):
        while is_worker_running():
            d = in_q.rd()
            out_q.wr(d)


@testbench
def test(p04):
    p04.in_q.wr(1)
    p04.in_q.wr(2)
    p04.in_q.wr(3)
    p04.in_q.wr(4)
    assert 1 == p04.out_q.rd()
    assert 2 == p04.out_q.rd()
    assert 3 == p04.out_q.rd()
    assert 4 == p04.out_q.rd()


p04 = Port04()
test(p04)
