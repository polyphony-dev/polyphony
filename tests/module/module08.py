from polyphony import module
from polyphony import testbench
from polyphony.io import Uint


@module
class ModuleTest08:
    def __init__(self):
        self.idata_a = Uint(width=16, protocol='valid')
        self.idata_b = Uint(width=16, protocol='valid')
        self.odata_a = Uint(width=16, protocol='ready_valid')
        self.odata_b = Uint(width=16, protocol='ready_valid')
        self.append_worker(self.worker, 'foo', self.idata_a, self.odata_a)
        self.append_worker(self.worker, 'bar', self.idata_b, self.odata_b)

    def worker(self, name, i, o):
        v = i()
        sm = 0
        data = [v] * 10
        for d in data:
            sm += d
            print(name, sm)
        o(sm)


@testbench
def test(m):
    m.idata_a(100)
    m.idata_b(200)
    assert m.odata_a() == 100 * 10
    assert m.odata_b() == 200 * 10


m = ModuleTest08()
test(m)
