from polyphony import module, testbench
from polyphony.io import Port
from polyphony.timing import wait_value


class Config:
    def __init__(self, width):
        self.width = width


@module
class CtorObj:
    def __init__(self, cfg):
        self.cfg = cfg
        self.o = Port(int, 'out')
        self.append_worker(self.work)

    def work(self):
        self.o.wr(self.cfg.width)


@testbench
def test0():
    cfg = Config(8)
    m = CtorObj(cfg)
    wait_value(8, m.o)
    assert m.o.rd() == 8
