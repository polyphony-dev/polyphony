"""3-level nested module: GrandChild -> Child -> Parent
Error: qualified_symbols fails to resolve 3-level attribute chain
after inlining.

qsyms[-1]='rd' (type=str) for var=self.gc.i.rd in scope=@top.Parent.gc_run_0
"""
from polyphony import module, is_worker_running
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


top = Parent()
