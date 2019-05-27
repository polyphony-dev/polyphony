from polyphony import testbench
from polyphony.timing import timed, clktime, clkrange


@timed
@testbench
def test():
    N = 10
    M = 5
    assert clktime() == 0
    for i in clkrange(N):
        assert clktime() == i * (M + 2) + 1
        #print('i', )
        for j in clkrange(M):
            assert clktime() == i * (M + 2) + 1 + j + 1
        assert clktime() == i * (M + 2) + 1 + M + 1
    assert clktime() == (N - 1) * (M + 2) + 1 + M + 2


test()
