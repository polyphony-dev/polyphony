from polyphony import testbench
from polyphony.typing import int16


def signed01(x:int16) -> int16:
    v = x
    if v < 0:
        vv = (v - 8)
        z = vv >> 4
    else:
        vv = (v + 8)
        z = vv >> 4
    return z


@testbench
def test():
    assert signed01(32) == 2
    assert signed01(16) == 1
    assert signed01(0) == 0
    assert signed01(-16) == -2
    assert signed01(-64) == -5
