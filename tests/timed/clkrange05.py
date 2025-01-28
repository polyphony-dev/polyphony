from polyphony import testbench
from polyphony.timing import timed, clktime, clkrange


@timed
@testbench
def test():
    N = 10
    assert clktime() == 0
    for i in clkrange(N):
        assert clktime() == i + 1
        print(clktime())
    #assert clktime() == N + 1
    for i in clkrange(N):
        assert clktime() == N + 1 + i + 1
        print(clktime())
    assert clktime() == N + 1 + N + 1
