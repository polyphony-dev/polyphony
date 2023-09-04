from polyphony import testbench
from polyphony import pipelined


def pipe17_func(xs0, ys0, ys1):
    for i in pipelined(range(len(xs0))):
    #for i in range(len(xs0)):
        x = xs0[i]
        if x:
            ys0[i] = ys1[i]
        else:
            ys1[i] = ys0[i]


def pipe17():
    data0 = [1, 1, 0, 0, 1, 0]
    data1 = [1, 2, 3, 4, 5, 6]
    data2 = [7, 8, 9, 10, 11, 12]
    pipe17_func(data0, data1, data2)
    assert 7 == data1[0]
    assert 8 == data1[1]
    assert 3 == data1[2]
    assert 4 == data1[3]
    assert 11 == data1[4]
    assert 6 == data1[5]

    assert 7 == data2[0]
    assert 8 == data2[1]
    assert 3 == data2[2]
    assert 4 == data2[3]
    assert 11 == data2[4]
    assert 6 == data2[5]


@testbench
def test():
    pipe17()

test()
