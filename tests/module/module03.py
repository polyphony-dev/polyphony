from polyphony import module
from polyphony import testbench
from polyphony import is_worker_running
from polyphony.timing import timed, clkfence, wait_rising
from polyphony.io import Port


@timed
@module
class ModuleTest03:
    def __init__(self):
        self.idata = Port(int, 'in')
        self.ivalid = Port(bool, 'in')
        self.odata = Port(int, 'out')
        self.ovalid = Port(bool, 'out')
        self.t0 = Port(int, 'any')
        self.t0valid = Port(bool, 'any')
        self.t1 = Port(int, 'any')
        self.t1valid = Port(bool, 'any')
        self.append_worker(pow, self.idata, self.ivalid,  self.t0,    self.t0valid)
        self.append_worker(pow, self.t0,    self.t0valid, self.t1,    self.t1valid)
        self.append_worker(pow, self.t1,    self.t1valid, self.odata, self.ovalid)


def pow(idata, ivalid, odata, ovalid):
    while is_worker_running():
        print('1')
        wait_rising(ivalid)
        d = idata.rd()
        odata.wr(d * d)
        print(d)
        clkfence()
        ovalid.wr(True)
        clkfence()
        ovalid.wr(False)


@timed
@testbench
def test(m):
    print('test 1')
    m.idata.wr(2)
    m.ivalid.wr(True)
    clkfence()
    print('test 2')
    m.ivalid.wr(False)
    wait_rising(m.ovalid)
    print('test 3')
    assert m.odata.rd() == 256

    m.idata.wr(4)
    m.ivalid.wr(True)
    clkfence()
    m.ivalid.wr(False)
    wait_rising(m.ovalid)
    print('2')
    assert m.odata.rd() == 65536


m = ModuleTest03()
test(m)
