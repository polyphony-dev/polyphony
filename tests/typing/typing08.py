import polyphony
from polyphony import testbench
from polyphony.typing import bit, bit8, int8


def typing08(a:bit8) -> int8:
    assert a > 0    # This will throw AssertionError in Python interpreter
    b:int8  = a
    assert b < 0
    return b

@testbench
def test():
    assert typing08(-1) < 0

test()
