from polyphony import testbench
from polyphony.typing import int16, int64
from polyphony.timing import clktime

def signed02(x:int16) -> int64:
    v = x
    if v < 0:
        t = clktime()
    else:
        t = 100
    return t


@testbench
def test():
    print(signed02(1))
    print(signed02(0))
    print(signed02(-1))
