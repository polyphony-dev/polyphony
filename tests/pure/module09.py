from polyphony import module, pure
from polyphony import testbench
from polyphony import is_worker_running
from polyphony.io import Queue
from polyphony.typing import uint16


@module
class ModuleTest09:
    @pure
    def __init__(self, data_size):
        self.i_q = Queue(uint16, maxsize=data_size)
        self.o_q = Queue(uint16, maxsize=data_size)
        tmp_q0 = Queue(uint16, maxsize=data_size)
        tmp_q1 = Queue(uint16, maxsize=data_size)
        self.append_worker(mul, 2, data_size, self.i_q, tmp_q0)
        self.append_worker(mul, 3, data_size, tmp_q0, tmp_q1)
        self.append_worker(mul, 4, data_size, tmp_q1, self.o_q)


def mul(factor, data_size, i_q, o_q):
    while is_worker_running():
        data = [None] * data_size
        for i in range(data_size):
            data[i] = i_q.rd()

        for i in range(data_size):
            data[i] *= factor

        for i in range(data_size):
            o_q.wr(data[i])


DATA_SIZE = 4
@testbench
def test(m):
    for i in range(DATA_SIZE):
        m.i_q.wr(i)

    for i in range(DATA_SIZE):
        d = m.o_q.rd()
        print(d)
        assert d == i * (2 * 3 * 4)


m = ModuleTest09(DATA_SIZE)
test(m)

