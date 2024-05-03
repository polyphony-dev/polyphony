from polyphony import testbench, module
from polyphony.io import Port
from polyphony.typing import int8, int16
from polyphony.timing import timed, clkfence


@timed
@module
class TestIF:
    def __init__(self, width):
        if width == 8:
            self.port = Port(int8, 'in')
        else:
            self.port = Port(int16, 'out', 0)
    def read(self):
        return self.port.rd()

    def write(self, v):
        self.port.wr(v)


@timed
@module
class interface01:
    def __init__(self):
        self.i = TestIF(8)
        self.o = TestIF(16)
        self.v = 0
        self.append_worker(self.main)

    def main(self):
        # 0
        clkfence()
        # 1
        self.v = self.i.read()
        clkfence()
        # 2
        self.o.write(self.v)
        clkfence()
        # 3
        clkfence()
        # 4
        self.o.write(self.i.read())
        clkfence()
        # 5


@timed
@testbench
def test():
    p01 = interface01()
    # 0
    p01.i.write(1)
    clkfence()
    # 1
    # read from in0 at module
    clkfence()
    # 2
    # write to out0 at module
    clkfence()
    # 3
    print(p01.o.read())
    assert 1 == p01.o.read()
    p01.i.write(2)
    clkfence()
    # 4
    # read and write at module
    clkfence()
    # 5
    print(p01.o.read())
    assert 2 == p01.o.read()
    #clkfence()
