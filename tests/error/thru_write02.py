#Cannot write to thru'd output port 'o'
from polyphony import module, is_worker_running
from polyphony.io import Port, thru, connect
from polyphony.typing import int8


@module
class Sub1:
    def __init__(self):
        self.o = Port(int8, 'out')
        self.append_worker(self.run)

    def run(self):
        while is_worker_running():
            self.o.wr(1)


@module
class Sub2:
    def __init__(self):
        self.i = Port(int8, 'in')
        self.append_worker(self.run)

    def run(self):
        while is_worker_running():
            self.i.rd()


@module
class Top:
    def __init__(self):
        self.o = Port(int8, 'out')
        self.sub1 = Sub1()
        self.sub2 = Sub2()
        thru(self.o, self.sub1.o)
        connect(self.o, self.sub2.i)  # ERROR: thru'd output に connect


top = Top()
