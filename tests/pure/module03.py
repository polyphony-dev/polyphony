from polyphony import module, pure
from polyphony import testbench
from polyphony import is_worker_running
from polyphony.timing import clkfence, wait_rising
from polyphony.io import Port


@module
class ModuleTest03:
    @pure
    def __init__(self):
        self.idata = Port(int, 'in')
        self.ivalid = Port(bool, 'in')
        self.odata = Port(int, 'out')
        self.ovalid = Port(bool, 'out')
        t0 = Port(int, 'any')
        t0valid = Port(bool, 'any')
        t1 = Port(int, 'any')
        t1valid = Port(bool, 'any')
        self.append_worker(pow, self.idata, self.ivalid, t0, t0valid)
        self.append_worker(pow, t0, t0valid, t1, t1valid)
        self.append_worker(pow, t1, t1valid, self.odata, self.ovalid)


def pow(idata, ivalid, odata, ovalid):
    while is_worker_running():
        wait_rising(ivalid)
        d = idata.rd()
        odata.wr(d * d)
        clkfence()
        ovalid.wr(True)
        ovalid.wr(False)


@testbench
def test(m):
    m.idata.wr(2)
    m.ivalid.wr(True)
    m.ivalid.wr(False)
    wait_rising(m.ovalid)
    assert m.odata.rd() == 256

    m.idata.wr(4)
    m.ivalid.wr(True)
    m.ivalid.wr(False)
    wait_rising(m.ovalid)
    assert m.odata.rd() == 65536


m = ModuleTest03()
test(m)
