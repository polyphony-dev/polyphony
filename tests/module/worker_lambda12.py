"""Lambda capturing a tuple ctor parameter as a free variable.

Tests that a tuple passed as a ctor parameter is propagated to
a worker scope when captured as a free variable in a lambda closure.
"""
from polyphony import module, testbench
from polyphony.io import Port
from polyphony.timing import wait_value


@module
class WorkerLambda12:
    def __init__(self, coeffs):
        self.o = Port(int, 'out')
        self.append_worker(self.work, lambda x: x * coeffs[0] + coeffs[1])

    def work(self, fn):
        self.o.wr(fn(10))


@testbench
def test():
    m = WorkerLambda12((3, 5))
    wait_value(35, m.o)
    assert m.o.rd() == 35
