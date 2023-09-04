import polyphony
from polyphony import testbench
from polyphony.typing import bit, Tuple


bits = (1, 0)  # type: Tuple[bit, bit]

@testbench
def test():
    assert 1 == bits[0]
    assert 0 == bits[1]


test()
