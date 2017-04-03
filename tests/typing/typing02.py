from polyphony import testbench
from polyphony.typing import List, bit, int8


def typing02_a(xs:List[bit], i:int8) -> bit:
    return xs[i]


def typing02_b(xs:List[int], i:int8) -> bit:
    return xs[i]


@testbench
def test():
    data = [0, 1, 1, 0,
            1, 0, 1, 0]  # type: List[bit]
    for i in range(len(data)):
        d = data[i]
        assert d == typing02_a(data, i)
        assert d == typing02_b(data, i)


test()
