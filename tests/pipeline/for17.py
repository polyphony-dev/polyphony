from polyphony import testbench
from polyphony import pipelined


def pipe17(xs0, xs1):
    for i in pipelined(range(len(xs0))):
        v = xs1[xs0[i]]
        xs1[xs0[i]] = xs1[v % 4]


@testbench
def test():
    data0 = [0, 0, 0, 1]
    data1 = [1, 2, 3, 4]
    pipe17(data0, data1)
    assert 4 == data1[0]
    assert 3 == data1[1]
    assert 3 == data1[2]
    assert 4 == data1[3]


test()
