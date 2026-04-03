#connect() requires ports with opposite directions, got 'in' and 'in'
from polyphony import module, is_worker_running
from polyphony.io import Port, connect
from polyphony.typing import int8


@module
class Sub:
    def __init__(self):
        self.i = Port(int8, 'in')
        self.append_worker(self.run)

    def run(self):
        while is_worker_running():
            pass


@module
class Top:
    def __init__(self):
        self.i = Port(int8, 'in')
        self.sub = Sub()
        connect(self.i, self.sub.i)  # ERROR: same direction


top = Top()
