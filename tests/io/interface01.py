from polyphony import testbench, module
from polyphony.io import Port, interface
from polyphony.typing import int8
from polyphony.timing import timed, clkfence

#@interface
# interfaceクラスは複数のPortを持ちそれらへのアクセスをメソッドとして
# 提供する
# interfaceの持つPortは、interfaceクラスを生成する親moduleのPortとして展開される
@interface
@timed
class TestIF:
    def __init__(self, dtype, direction, init=None):
        self.port = Port(dtype, direction, init)

    def read(self):
        return self.port.rd()

    def write(self, v):
        self.port.wr(v)


@timed
@module
class interface01:
    def __init__(self):
        self.i = TestIF(int8, 'in')
        self.o = TestIF(int8, 'out', 0)
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
@testbench(target=interface01)
def test(p01):
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



p01 = interface01()
test(p01)
