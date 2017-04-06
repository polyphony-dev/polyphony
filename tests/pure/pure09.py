from polyphony import pure
from polyphony import testbench


@pure
def mul(data):
    return [d * d for d in data]


def pure09_a(idx):
    data = mul([1, 2, 3, 4, 5])
    return data[idx]


def pure09_b(idx):
    data = mul([2] * 10)
    return data[idx]


@testbench
def test():
    assert 1 == pure09_a(0)
    assert 4 == pure09_a(1)
    assert 9 == pure09_a(2)

    assert 4 == pure09_b(0)


test()
