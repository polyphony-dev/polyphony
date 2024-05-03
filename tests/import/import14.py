from polyphony import module
from polyphony import testbench
from polyphony.modules import Handshake
from sub4 import sub_worker as worker


@module
class import14:
    def __init__(self):
        self.i = Handshake(int, 'in')
        self.o = Handshake(int, 'out')
        self.append_worker(worker, self.i, self.o)


@testbench
def test():
    m = import14()
    m.i.wr(1)
    assert 2 == m.o.rd()
    m.i.wr(2)
    assert 3 == m.o.rd()
    m.i.wr(10)
    assert 11 == m.o.rd()
