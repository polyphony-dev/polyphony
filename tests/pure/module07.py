from polyphony import module, pure
from polyphony import testbench
from polyphony.io import Port
from polyphony.typing import uint16


@module
class ModuleTest07:
    @pure
    def __init__(self):
        self.idata_a = Port(uint16, 'in', protocol='valid')
        self.idata_b = Port(uint16, 'in', protocol='valid')
        self.odata_a = Port(uint16, 'out', protocol='ready_valid')
        self.odata_b = Port(uint16, 'out', protocol='ready_valid')
        self.append_worker(self.worker, 'foo', self.idata_a, self.odata_a)
        self.append_worker(self.worker, 'bar', self.idata_b, self.odata_b)

    def worker(self, name, i, o):
        v = i()
        prod = 0
        data = [1, 2, 3, 4, 5]
        for d in data:
            prod += d * v
            print(name, prod)
        o(prod)


@testbench
def test(m):
    m.idata_a(100)
    m.idata_b(200)
    assert m.odata_a() == (1 + 2 + 3 + 4 + 5) * 100
    assert m.odata_b() == (1 + 2 + 3 + 4 + 5) * 200


m = ModuleTest07()
test(m)
