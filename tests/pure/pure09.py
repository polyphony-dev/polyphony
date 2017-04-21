from polyphony import pure
from polyphony import testbench


@pure
def mul(data):
    return [d * d for d in data]


def pure09_a(i0, i1, i2):
    data = mul([1, 2, 3, 4, 5])
    return data[i0] + data[i1] + data[i2]


def pure09_b(i0, i1, i2):
    data = mul([2] * 10)
    return data[i0] + data[i1] + data[i2]


@testbench
def test():
    assert 1 + 4 + 9 == pure09_a(0, 1, 2)
    assert 4 + 9 + 16 == pure09_a(1, 2, 3)
    assert 9 + 16 + 25 == pure09_a(2, 3, 4)

    assert 4 + 4 + 4 == pure09_b(0, 1, 2)


test()
