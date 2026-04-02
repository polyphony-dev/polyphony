"""Port I/O scoping: submodule ports are NOT promoted to parent I/O.

Only the top module's own Port fields become Verilog I/O.
Submodule ports are connected via internal wires through module
instantiation, not exposed as parent-level I/O.

This test verifies the basic nesting pattern where the parent has
no workers and the testbench accesses submodule ports directly.
"""
from polyphony import module, testbench, is_worker_running
from polyphony.io import Port
from polyphony.typing import int8
from polyphony.timing import clksleep


@module
class Inner:
    def __init__(self, scale):
        self.i = Port(int8, 'in')
        self.o = Port(int8, 'out')
        self.scale = scale
        self.append_worker(self.run)

    def run(self):
        while is_worker_running():
            self.o.wr(self.i.rd() * self.scale)


@module
class Outer:
    def __init__(self):
        self.a = Inner(2)
        self.b = Inner(5)


@testbench
def test():
    m = Outer()
    m.a.i.wr(3)
    m.b.i.wr(4)
    clksleep(10)
    assert m.a.o.rd() == 6
    assert m.b.o.rd() == 20
