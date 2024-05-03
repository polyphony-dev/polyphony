from polyphony import testbench
from polyphony.timing import timed, clktime, clkrange


@timed
@testbench
def test():
    N = 10
    assert clktime() == 0
    for i in clkrange(N):
        assert clktime() == i + 1
    assert clktime() == N + 1
