from polyphony import module
from polyphony import testbench
from polyphony import is_worker_running
from polyphony.timing import clkfence, wait_rising
from polyphony.io import Int, Bit


@module
class WorkerTest03:
    def __init__(self):
        self.idata = Int()
        self.ivalid = Bit()
        self.odata = Int()
        self.ovalid = Bit()
        t0 = Int()
        t0valid = Bit()
        t1 = Int()
        t1valid = Bit()
        self.append_worker(self.pow, self.idata, self.ivalid, t0, t0valid)
        self.append_worker(self.pow, t0, t0valid, t1, t1valid)
        self.append_worker(self.pow, t1, t1valid, self.odata, self.ovalid)

    def pow(self, idata, ivalid, odata, ovalid):
        while is_worker_running():
            wait_rising(ivalid)
            d = idata.rd()
            odata.wr(d * d)
            clkfence()
            ovalid.wr(1)


@testbench
def test(wtest):
    wtest.idata.wr(2)
    wtest.ivalid.wr(1)
    wait_rising(wtest.ovalid)
    assert wtest.odata.rd() == 256


w = WorkerTest03()
test(w)
