from polyphony import testbench
from polyphony.typing import List, bit, int8


def typing03_a(xs:List[bit][8], i:int8) -> bit:
    return xs[i]


def typing03_b(xs:List[int][8], i:int8) -> bit:
    return xs[i]


@testbench
def test():
    data = [0, 1, 1, 0,
            1, 0, 1, 0]  # type: List[bit][8]
    for i in range(len(data)):
        d = data[i]
        assert d == typing03_a(data, i)
        assert d == typing03_b(data, i)


test()
