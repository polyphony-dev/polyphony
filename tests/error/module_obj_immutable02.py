#Cannot write to field 'width' of object argument in @module class
from polyphony import module, testbench
from polyphony.io import Port


class Config:
    def __init__(self, width):
        self.width = width


@module
class M:
    def __init__(self, cfg):
        self.cfg = cfg
        self.cfg.width = 99
        self.p = Port(int, 'out')
        self.append_worker(self.run)

    def run(self):
        self.p.wr(self.cfg.width)


@testbench
def test():
    cfg = Config(8)
    m = M(cfg)
