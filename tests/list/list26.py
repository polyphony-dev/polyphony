from polyphony import testbench


def list26(xs, i):
    return xs[i]


@testbench
def test():
    data1 = [0, 1, 2]
    data2 = [3, 4, 5]
    for i in range(len(data1)):
        d = data1[i]
        assert d == list26(data1, i)

    for i in range(len(data2)):
        d = data2[i]
        assert d == list26(data2, i)


test()