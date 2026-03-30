"""Lambda capturing a function ctor parameter as a free variable.

Tests that a function passed as a ctor parameter is propagated to
a worker scope when captured as a free variable in a lambda closure.
"""
from polyphony import module, testbench
from polyphony.io import Port
from polyphony.timing import wait_value


def double(x):
    return x * 2


@module
class WorkerLambda11:
    def __init__(self, fn):
        self.o = Port(int, 'out')
        self.append_worker(self.work, lambda x: fn(x) + 1)

    def work(self, g):
        self.o.wr(g(20))


@testbench
def test():
    m = WorkerLambda11(double)
    wait_value(41, m.o)
    assert m.o.rd() == 41
