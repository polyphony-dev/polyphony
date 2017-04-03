from polyphony import module
from polyphony import testbench
from polyphony import is_worker_running
from polyphony.timing import clkfence, wait_rising
from polyphony.io import Port


@module
class ModuleTest03:
    def __init__(self):
        self.idata = Port(int)
        self.ivalid = Port(bool)
        self.odata = Port(int)
        self.ovalid = Port(bool)
        t0 = Port(int)
        t0valid = Port(bool)
        t1 = Port(int)
        t1valid = Port(bool)
        self.append_worker(pow, self.idata, self.ivalid, t0, t0valid)
        self.append_worker(pow, t0, t0valid, t1, t1valid)
        self.append_worker(pow, t1, t1valid, self.odata, self.ovalid)


def pow(idata, ivalid, odata, ovalid):
    while is_worker_running():
        wait_rising(ivalid)
        d = idata.rd()
        odata.wr(d * d)
        clkfence()
        ovalid.wr(1)
        ovalid.wr(0)


@testbench
def test(m):
    m.idata.wr(2)
    m.ivalid.wr(1)
    m.ivalid.wr(0)
    wait_rising(m.ovalid)
    assert m.odata.rd() == 256

    m.idata.wr(4)
    m.ivalid.wr(1)
    m.ivalid.wr(0)
    wait_rising(m.ovalid)
    assert m.odata.rd() == 65536


m = ModuleTest03()
test(m)
