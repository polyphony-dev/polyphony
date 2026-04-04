#Cannot read from submodule's input port 'ready'
# CONFIG {"flatten_modules":false}
from polyphony import module, is_worker_running
from polyphony.io import Port
from polyphony.modules import Handshake
from polyphony.typing import int8


@module
class Sub:
    def __init__(self):
        self.hs_out = Handshake(int8, 'out')
        self.append_worker(self.run)

    def run(self):
        while is_worker_running():
            self.hs_out.wr(42)


@module
class Top:
    def __init__(self):
        self.sub = Sub()
        self.append_worker(self.worker)

    def worker(self):
        self.sub.hs_out.wr(99)  # ERROR: wr() on submodule's output Handshake


top = Top()
