#Writing to 'p' is conflicted
from polyphony import testbench
from polyphony import module
from polyphony.io import Port
from .sub import Sub


@module
class io_write_conflict05:
    def __init__(self):
        self.sub = Sub()
        self.append_worker(self.w)
        self.append_worker(self.w)

    def w(self):
        self.sub.p.wr(1)


@testbench
def test(m):
    m.sub.p.wr(0)


m = io_write_conflict05()
test(m)
