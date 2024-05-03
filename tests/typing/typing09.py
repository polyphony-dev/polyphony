import polyphony
from polyphony import testbench
from polyphony.typing import bit, Tuple


bits = (1, 0)  # type: Tuple[bit, bit]


def typing09(i):
    return bits[i]


@testbench
def test():
    assert 1 == typing09(0)
    assert 0 == typing09(1)
