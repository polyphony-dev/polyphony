from polyphony import module
from polyphony import testbench
from polyphony import is_worker_running
from polyphony.modules import Handshake
from sub4 import VALUE as Value
from sub3 import SUB3_GLOBAL_ARRAY1 as SUB3_GLOBAL_ARRAY

@module
class import13:
    def __init__(self):
        self.x = Value
        self.o = Handshake(int, 'out')
        self.append_worker(self.w)

    def w(self):
        while is_worker_running():
            for i in range(len(SUB3_GLOBAL_ARRAY)):
                self.o.wr(self.x + SUB3_GLOBAL_ARRAY[i])


@testbench
def test():
    m = import13()
    assert Value + SUB3_GLOBAL_ARRAY[0] == m.o.rd()
    assert Value + SUB3_GLOBAL_ARRAY[1] == m.o.rd()
    assert Value + SUB3_GLOBAL_ARRAY[2] == m.o.rd()
    assert Value + SUB3_GLOBAL_ARRAY[3] == m.o.rd()
