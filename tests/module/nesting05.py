from polyphony import module
from polyphony import testbench
from polyphony import is_worker_running
from polyphony.io import Port
from polyphony.typing import int8
from polyphony.timing import wait_value
from polyphony.modules import Handshake


@module
class SubWithHandshake:
    def __init__(self):
        self.hs_in = Handshake(int8, 'in')
        self.hs_out = Handshake(int8, 'out')
        self.append_worker(self.worker)

    def worker(self):
        while is_worker_running():
            v = self.hs_in.rd()
            self.hs_out.wr(v * 2)


@module
class Nesting05:
    def __init__(self):
        self.sub = SubWithHandshake()
        self.append_worker(self.worker)
        self.start = Port(bool, 'in', init=False)
        self.result = Handshake(int8, 'out')

    def worker(self):
        wait_value(True, self.start)
        self.sub.hs_in.wr(5)
        v = self.sub.hs_out.rd()
        self.result.wr(v)


@testbench
def test():
    m = Nesting05()
    m.start.wr(True)
    assert 10 == m.result.rd()
