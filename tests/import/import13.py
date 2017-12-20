from polyphony import module
from polyphony import testbench
from polyphony import is_worker_running
from polyphony.io import Port
from sub4 import VALUE as Value
from sub3 import SUB3_GLOBAL_ARRAY

@module
class import13:
    def __init__(self):
        self.x = Value
        self.o = Port(int, 'out', protocol='ready_valid')
        self.append_worker(self.w)

    def w(self):
        while is_worker_running():
            for i in range(len(SUB3_GLOBAL_ARRAY)):
                self.o.wr(self.x + SUB3_GLOBAL_ARRAY[i])


@testbench
def test(m):
    assert Value + SUB3_GLOBAL_ARRAY[0] == m.o.rd()
    assert Value + SUB3_GLOBAL_ARRAY[1] == m.o.rd()
    assert Value + SUB3_GLOBAL_ARRAY[2] == m.o.rd()
    assert Value + SUB3_GLOBAL_ARRAY[3] == m.o.rd()


m = import13()
test(m)
