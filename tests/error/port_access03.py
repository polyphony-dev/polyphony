#Cannot read from submodule's input port 'valid'
# CONFIG {"flatten_modules":false}
from polyphony import module, is_worker_running
from polyphony.io import Port
from polyphony.modules import Handshake
from polyphony.typing import int8


@module
class Sub:
    def __init__(self):
        self.hs_in = Handshake(int8, 'in')
        self.append_worker(self.run)

    def run(self):
        while is_worker_running():
            v = self.hs_in.rd()


@module
class Top:
    def __init__(self):
        self.sub = Sub()
        self.append_worker(self.worker)

    def worker(self):
        v = self.sub.hs_in.rd()  # ERROR: rd() on submodule's input Handshake


top = Top()
