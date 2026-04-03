#thru() requires both ports to have the same direction, got 'in' and 'out'
from polyphony import module, is_worker_running
from polyphony.io import Port, thru
from polyphony.typing import int8


@module
class Sub:
    def __init__(self):
        self.i = Port(int8, 'in')
        self.o = Port(int8, 'out')
        self.append_worker(self.run)

    def run(self):
        while is_worker_running():
            self.o.wr(self.i.rd())


@module
class Top:
    def __init__(self):
        self.i = Port(int8, 'in')
        self.o = Port(int8, 'out')
        self.sub = Sub()
        thru(self.i, self.sub.o)  # ERROR: in と out で direction 不一致


top = Top()
