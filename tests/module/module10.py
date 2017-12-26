from polyphony import module
from polyphony import testbench
from polyphony import is_worker_running
from polyphony.io import Port
from polyphony.timing import clkfence


@module
class ModuleTest10:
    def __init__(self):
        self.idata = Port(int, 'in', protocol='ready_valid')
        self.odata = Port(int, 'out', protocol='ready_valid')
        t0 = Port(int, 'any', protocol='ready_valid')
        t1 = Port(int, 'any', protocol='ready_valid')
        self.append_worker(pow, self.idata, t0)
        self.append_worker(pow, t0, t1)
        self.append_worker(pow, t1, self.odata)


def pow(idata, odata):
    while is_worker_running():
        d = idata.rd()
        odata.wr(d * d)


@testbench
def test(m):
    m.idata.wr(2)
    m.idata.wr(3)
    m.idata.wr(4)
    clkfence()
    assert m.odata.rd() == 256
    assert m.odata.rd() == 6561
    assert m.odata.rd() == 65536


m = ModuleTest10()
test(m)
