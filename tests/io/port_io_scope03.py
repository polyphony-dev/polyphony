"""Port I/O scoping: multiple nesting levels.

Two levels of nesting: Top -> Mid -> Leaf.
Each level's own ports are its own I/O; submodule ports stay internal.
"""
from polyphony import module, testbench, is_worker_running
from polyphony.io import Port
from polyphony.typing import int8
from polyphony.timing import clksleep


@module
class Leaf:
    def __init__(self, factor):
        self.i = Port(int8, 'in')
        self.o = Port(int8, 'out')
        self.factor = factor
        self.append_worker(self.run)

    def run(self):
        while is_worker_running():
            self.o.wr(self.i.rd() * self.factor)


@module
class Mid:
    def __init__(self):
        self.leaf1 = Leaf(2)
        self.leaf2 = Leaf(3)


@module
class Top:
    def __init__(self):
        self.m1 = Mid()
        self.m2 = Mid()


@testbench
def test():
    t = Top()
    t.m1.leaf1.i.wr(5)
    t.m1.leaf2.i.wr(10)
    t.m2.leaf1.i.wr(7)
    t.m2.leaf2.i.wr(4)
    clksleep(10)
    assert t.m1.leaf1.o.rd() == 10
    assert t.m1.leaf2.o.rd() == 30
    assert t.m2.leaf1.o.rd() == 14
    assert t.m2.leaf2.o.rd() == 12
