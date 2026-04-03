#Cannot write to field 'value' of object argument in @module class
from polyphony import module, is_worker_running
from polyphony.io import Port
from polyphony.typing import int8


@module
class Sub:
    def __init__(self):
        self.i = Port(int8, 'in')
        self.o = Port(int8, 'out')
        self.value = 0
        self.append_worker(self.run)

    def run(self):
        while is_worker_running():
            self.o.wr(self.i.rd() + self.value)


@module
class Parent:
    def __init__(self):
        self.sub = Sub()
        self.append_worker(self.worker)

    def worker(self):
        self.sub.value = 99  # ERROR: cannot write to submodule field


top = Parent()
