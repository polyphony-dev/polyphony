#Cannot write to submodule port '_hidden' from parent module
from polyphony import module, is_worker_running
from polyphony.io import Port
from polyphony.typing import int8


@module
class Sub:
    def __init__(self):
        self.i = Port(int8, 'in')
        self.o = Port(int8, 'out')
        self._hidden = Port(int8, 'out')
        self.append_worker(self.run)

    def run(self):
        while is_worker_running():
            self.o.wr(self.i.rd())
            self._hidden.wr(self.i.rd())


@module
class Top:
    def __init__(self):
        self.sub = Sub()
        self.append_worker(self.worker)

    def worker(self):
        self.sub._hidden.wr(10)  # ERROR: private port write from parent


top = Top()
