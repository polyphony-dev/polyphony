"""Basic: pass module instance as constructor arg, access its ports."""
from polyphony import module, testbench, is_worker_running
from polyphony.io import Port
from polyphony.typing import int8
from polyphony.timing import clksleep


@module
class Provider:
    def __init__(self):
        self.i = Port(int8, 'in')
        self.o = Port(int8, 'out')
        self.append_worker(self.run)

    def run(self):
        while is_worker_running():
            self.o.wr(self.i.rd() * 2)


@module
class Consumer:
    def __init__(self, src):
        self.result = Port(int8, 'out')
        self.append_worker(self.run, src)

    def run(self, src):
        src.i.wr(5)
        clksleep(5)
        self.result.wr(src.o.rd())


@module
class Top:
    def __init__(self):
        self.prov = Provider()
        self.cons = Consumer(self.prov)


@testbench
def test():
    m = Top()
    clksleep(20)
    assert m.cons.result.rd() == 10
