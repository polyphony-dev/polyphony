"""Port I/O scoping: parent's own ports are I/O, submodule ports are internal.

The parent module has its own Port fields (data_in, data_out) which
become Verilog I/O. The submodule's ports are connected internally
and not exposed at the parent level.
"""
from polyphony import module, testbench, is_worker_running
from polyphony.io import Port
from polyphony.typing import int8
from polyphony.timing import clksleep


@module
class Doubler:
    def __init__(self):
        self.i = Port(int8, 'in')
        self.o = Port(int8, 'out')
        self.append_worker(self.run)

    def run(self):
        while is_worker_running():
            self.o.wr(self.i.rd() * 2)


@module
class Top:
    def __init__(self):
        self.data_in = Port(int8, 'in')
        self.data_out = Port(int8, 'out')
        self.sub = Doubler()


@testbench
def test():
    m = Top()
    m.data_in.wr(7)
    clksleep(10)
    print(m.data_in.rd())
    print(m.data_out.rd())
    print(m.sub.i.rd())
    print(m.sub.o.rd())
