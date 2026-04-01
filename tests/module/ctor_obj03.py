from polyphony import module, testbench
from polyphony.io import Port
from polyphony.timing import wait_value


class Config:
    def __init__(self, base):
        self.base = base


@module
class ModA:
    def __init__(self, cfg):
        self.cfg = cfg
        self.o = Port(int, 'out')
        self.append_worker(self.work)

    def work(self):
        self.o.wr(self.cfg.base + 1)


@module
class ModB:
    def __init__(self, cfg):
        self.cfg = cfg
        self.o = Port(int, 'out')
        self.append_worker(self.work)

    def work(self):
        self.o.wr(self.cfg.base + 2)


@testbench
def test0():
    cfg = Config(100)
    a = ModA(cfg)
    b = ModB(cfg)
    wait_value(101, a.o)
    assert a.o.rd() == 101
    wait_value(102, b.o)
    assert b.o.rd() == 102
