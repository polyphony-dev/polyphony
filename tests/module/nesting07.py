from polyphony import module, testbench, is_worker_running
from polyphony.io import Port
from polyphony.timing import clksleep
from polyphony.typing import int8


@module
class GrandChild:
    def __init__(self):
        self.i = Port(int8, 'in')
        self.o = Port(int8, 'out')
        self.append_worker(self.run)

    def run(self):
        while is_worker_running():
            self.o.wr(self.i.rd() * 3)


@module
class Child:
    def __init__(self):
        self.gc = GrandChild()
        self.i = Port(int8, 'in')
        self.o = Port(int8, 'out')
        self.append_worker(self.run)

    def run(self):
        while is_worker_running():
            self.gc.i.wr(self.i.rd())
            clksleep(3)
            self.o.wr(self.gc.o.rd())


@module
class Parent:
    def __init__(self):
        self.child = Child()
        self.i = Port(int8, 'in')
        self.o = Port(int8, 'out')
        self.append_worker(self.worker)

    def worker(self):
        while is_worker_running():
            self.child.i.wr(self.i.rd())
            clksleep(5)
            self.o.wr(self.child.o.rd())


@testbench
def test():
    m = Parent()
    m.i.wr(7)
    clksleep(20)
    expected = 7 * 3  # GrandChild multiplies by 3
    assert expected == m.o.rd()
