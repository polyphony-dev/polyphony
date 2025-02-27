from polyphony import testbench
from polyphony.timing import timed, clktime, clkfence, clksleep


@timed
@testbench
def test():
    assert clktime() == 0
    clkfence()
    assert clktime() == 1
    clksleep(1)
    assert clktime() == 2
    clksleep(2)
    assert clktime() == 4

    prev = clktime()  # meta: symbol=register
    clksleep(10)
    assert clktime() == 14
    elapsed = clktime() - prev
    assert elapsed == 10
