from polyphony import testbench, module, is_worker_running
from polyphony.io import Queue, Port
from polyphony.typing import int8


@module
class queue06:
    def __init__(self):
        self.in_cmd = Queue(int8, 'in', maxsize=2)
        self.din0 = Port(int, 'in')
        self.din1 = Port(int, 'in')
        self.out_q = Queue(int8, 'out', maxsize=2)
        self.append_worker(self.main)

    def calc(self, cmd):
        if cmd == 0:
            return self.din0.rd() + self.din1.rd()
        elif cmd == 1:
            return self.din0.rd() - self.din1.rd()
        elif cmd == 2:
            return self.din0.rd() * self.din1.rd()
        return 0

    def main(self):
        while is_worker_running():
            if not self.in_cmd.empty():
                cmd = self.in_cmd.rd()
                ret = self.calc(cmd)
                if not self.out_q.full():
                    self.out_q.wr(ret)


@testbench
def test(q):
    q.din0.wr(1)
    q.din1.wr(2)
    q.in_cmd.wr(0)
    assert 3 == q.out_q.rd()

    q.din0.wr(1)
    q.din1.wr(2)
    q.in_cmd.wr(1)
    assert -1 == q.out_q.rd()

    q.din0.wr(1)
    q.din1.wr(2)
    q.in_cmd.wr(2)
    assert 2 == q.out_q.rd()


q = queue06()
test(q)
