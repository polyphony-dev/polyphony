from polyphony import testbench
from polyphony.typing import Tuple, bit, int8


def typing04_a(xs:Tuple[bit, bit, bit], i:int8) -> bit:
    return xs[i]


def typing04_b(xs:Tuple[int, int, int], i:int8) -> int:
    return xs[i]


def typing04():
    data = (0, 1, 1)  # type: Tuple[bit, bit, bit]
    for i in range(len(data)):
        d = data[i]
        assert d == typing04_a(data, i)
        assert d == typing04_b(data, i)


@testbench
def test():
    typing04()

test()
