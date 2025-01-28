from polyphony import testbench
from polyphony.typing import Tuple, bit, int8


def typing05_a(xs:Tuple[bit, ...], i:int8) -> bit:
    return xs[i]


def typing05_b(xs:Tuple[int, ...], i:int8) -> int:
    return xs[i]


def typing05():
    data = (0, 1, 1)  # type: Tuple[bit, ...]
    for i in range(len(data)):
        d = data[i]
        assert d == typing05_a(data, i)
        assert d == typing05_b(data, i)

@testbench
def test():
    typing05()
