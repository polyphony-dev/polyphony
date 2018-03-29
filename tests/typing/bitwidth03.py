from polyphony import testbench
from polyphony.typing import List, int16, int32, int64


def bitwidth03_a(x:int16, y:int16) -> int32:
    z:int64 = 0
    for i in range(16):
        z += x * y
    return z >> (16 - 1)


def bitwidth03_b(x:int16, y:int16) -> int32:
    z:List[int64] = [0]
    for i in range(16):
        z[0] += x * y
    return z[0] >> (16 - 1)


@testbench
def test():
    assert 15 == bitwidth03_a(1, 32767)
    assert -16 == bitwidth03_a(-1, 32767)
    assert 262136 == bitwidth03_a(32767, 16384)
    assert 524256 == bitwidth03_a(32767, 32767)
    assert -524257 == bitwidth03_a(-32767, 32767)

    assert 15 == bitwidth03_b(1, 32767)
    assert -16 == bitwidth03_b(-1, 32767)
    assert 262136 == bitwidth03_b(32767, 16384)
    assert 524256 == bitwidth03_b(32767, 32767)
    assert -524257 == bitwidth03_b(-32767, 32767)

test()
