#The pipeline may not work correctly if there is both read and write access to the same memory 'xs0'
from polyphony import testbench
from polyphony import pipelined


def pipeline_hazard01(xs0, xs1, xs2):
    for i in pipelined(range(len(xs0) - 1)):
        xs1[i] = xs0[i]
        xs0[i + 1] = xs2[i]


@testbench
def test():
    data0 = [1, 2, 3]
    data1 = [0, 0, 0]
    data2 = [1, 2, 1]
    pipeline_hazard01(data0, data1, data2)
    assert 1 == data0[0]
    assert 1 == data0[1]
    assert 2 == data0[2]
    assert 1 == data1[0]
    assert 1 == data1[1]
    assert 0 == data1[2]


test()
