#Cannot write to thru'd output port 'o'
from polyphony import module, is_worker_running
from polyphony.io import Port, thru
from polyphony.typing import int8


@module
class Sub:
    def __init__(self):
        self.o = Port(int8, 'out')
        self.append_worker(self.run)

    def run(self):
        while is_worker_running():
            self.o.wr(42)


@module
class Top:
    def __init__(self):
        self.o = Port(int8, 'out')
        self.sub = Sub()
        thru(self.o, self.sub.o)
        self.append_worker(self.worker)

    def worker(self):
        self.o.wr(99)  # ERROR: thru'd output に書き込み


top = Top()
