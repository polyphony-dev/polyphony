from polyphony import testbench


def list26_a(i):
    xs = [0, 1, 2]
    return xs[i]

def list26_b(i):
    xs = [3, 4, 5]
    return xs[i]


@testbench
def test():
    data1 = [0, 1, 2]
    data2 = [3, 4, 5]
    for i in range(len(data1)):
        d = data1[i]
        assert d == list26_a(i)

    for i in range(len(data2)):
        d = data2[i]
        assert d == list26_b(i)


test()