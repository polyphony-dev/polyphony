from polyphony import testbench, module
from polyphony.io import Port
from polyphony.typing import bit8
from polyphony.timing import timed, clkfence


@module
class watch_test:
    def __init__(self):
        self.i = Port(bit8, 'in')
        self.o = Port(bit8, 'out', 0)
        self.append_worker(self.main)

    @timed
    def main(self):
        clkfence()
        v = self.i.rd()
        clkfence()
        self.o.wr(v + 10)
        clkfence()


# watch() test: run manually with `python simu.py -P tests/timed/watch_test.py`
# and add `from polyphony.simulator import watch; watch(m.i, m.o)` after instantiation

@timed
@testbench
def test():
    m = watch_test()
    m.i.wr(5)
    clkfence()
    clkfence()
    clkfence()
    x = m.o.rd()
    assert x == 15
