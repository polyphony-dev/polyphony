from polyphony import module
from polyphony import testbench
from polyphony import is_worker_running
from polyphony.io import Queue
from polyphony.typing import uint16
from polyphony.timing import clksleep


@module
class ModuleTest11:
    def __init__(self):
        self.o1_q = Queue(uint16, 'out', maxsize=1)
        self.o2_q = Queue(uint16, 'out', maxsize=1)
        self.append_worker(self.w, self.o1_q, self.o2_q)

    def w(self, o1_q, o2_q):
        i = 0
        data = (1, 2, 3, 4, 5)
        while is_worker_running():
            d = data[i % 5]
            i += 1
            o1_q.wr(d)
            o2_q.wr(i)
            #print(i)


@testbench
def test(m):
    clksleep(10)
    for i in range(1, 6):
        print(i)
        x1 = m.o1_q.rd()
        assert x1 == i
        x2 = m.o2_q.rd()
        assert x2 == i


m = ModuleTest11()
test(m)
