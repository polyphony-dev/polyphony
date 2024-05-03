from polyphony import testbench
from polyphony import module
from polyphony.io import Port

VALUE = 100

@module
class sub4:
    def __init__(self, param=10):
        self.i = Port(int, 'in', init=VALUE)
        self.o = Port(int, 'out')
        self.param = param


def sub_worker(p0, p1):
    v = p0.rd()
    p1.wr(v + 1)


@testbench
def sub_test():
    pass
