#Cannot write to field 'value' of object argument in @module class
from polyphony import module, is_worker_running
from polyphony.io import Port
from polyphony.typing import int8


@module
class Target:
    def __init__(self):
        self.i = Port(int8, 'in')
        self.o = Port(int8, 'out')
        self.value = 0
        self.append_worker(self.run)

    def run(self):
        while is_worker_running():
            self.o.wr(self.i.rd())


@module
class Bad:
    def __init__(self, tgt):
        self.append_worker(self.run, tgt)

    def run(self, tgt):
        tgt.value = 99  # ERROR: cannot write to module instance field


@module
class Top:
    def __init__(self):
        self.tgt = Target()
        self.bad = Bad(self.tgt)


top = Top()
