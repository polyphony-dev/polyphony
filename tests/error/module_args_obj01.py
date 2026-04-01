#The type of @module class argument must be constant, not object
from polyphony import module, testbench
from polyphony.io import Port


@module
class Sub:
    def __init__(self):
        self.p = Port(int, 'out')
        self.append_worker(self.run)

    def run(self):
        self.p.wr(1)


@module
class Top:
    def __init__(self, sub):
        self.p = Port(int, 'out')
        self.append_worker(self.run)

    def run(self):
        self.p.wr(1)


@testbench
def test():
    s = Sub()
    m = Top(s)
