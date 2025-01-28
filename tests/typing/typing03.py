from polyphony import testbench
from polyphony.typing import List, bit, int8


def bitdata(xs:List[bit], i:int8) -> bit:
    return xs[i]


def intdata(xs:List[int], i:int8) -> int:
    return xs[i]


def typing03_a(i:int8) -> bit:
    data = [0, 1, 1, 0, 1, 0, 1, 0]  # type: List[bit]
    return bitdata(data, i)


def typing03_b(i:int8) -> int:
    data = [0, 1, 1, 0, 1, 0, 1, 0]  # type: List[int]
    return intdata(data, i)


@testbench
def test():
    data = [0, 1, 1, 0, 1, 0, 1, 0]
    for i in range(8):
        assert data[i] == typing03_a(i)
        assert data[i] == typing03_b(i)
