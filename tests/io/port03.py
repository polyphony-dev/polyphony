from polyphony import testbench, module, is_worker_running
from polyphony.io import Queue
from polyphony.typing import int8


@module
class Port03:
    def __init__(self):
        self.in_q = Queue(int8, maxsize=2)
        self.out_q = Queue(int8, maxsize=2)
        self.append_worker(self.main)

    def main(self):
        while is_worker_running():
            d = self.in_q.rd()
            self.out_q.wr(d)


@testbench
def test(p03):
    p03.in_q.wr(1)
    p03.in_q.wr(2)
    p03.in_q.wr(3)
    p03.in_q.wr(4)
    assert 1 == p03.out_q.rd()
    assert 2 == p03.out_q.rd()
    assert 3 == p03.out_q.rd()
    assert 4 == p03.out_q.rd()


p03 = Port03()
test(p03)
