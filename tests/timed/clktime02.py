from polyphony import testbench, Reg
from polyphony.timing import timed, clktime, clkfence, clksleep


@timed
@testbench
def test():
    assert clktime() == 0
    clksleep(1000001)
    assert clktime() == 1000001
