from polyphony import testbench
from polyphony import unroll


def unroll01(xs, ys):
    s = 0
    for i in unroll(range(8)):
        x = xs[i] + 1
        if x < 0:
            s = s + x
        else:
            s = s - x
        ys[i] = x
        #print(x)
    return s


@testbench
def test():
    data = [1, 2, 3, 4, 5, 6, 7, 8]
    out_data = [0] * 8
    s = unroll01(data, out_data)
    print(s)
    assert -44 == s
    assert 2 == out_data[0]
    assert 3 == out_data[1]
    assert 4 == out_data[2]
    assert 5 == out_data[3]
    assert 6 == out_data[4]
    assert 7 == out_data[5]
    assert 8 == out_data[6]
    assert 9 == out_data[7]


test()
