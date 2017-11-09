from polyphony import module
from polyphony import testbench
from polyphony import is_worker_running
from polyphony.io import Port
from sub4 import VALUE as Value


@module
class import13:
    def __init__(self):
        self.x = Value
        self.o = Port(int, 'out', protocol='ready_valid')
        self.append_worker(self.w)

    def w(self):
        while is_worker_running():
            self.o.wr(self.x)


@testbench
def test(m):
    assert Value == m.o.rd()


m = import13()
test(m)
