from polyphony import preprocess as pre
from polyphony import testbench


@pre
def mul(data):
    return [d * d for d in data]


def preprocess09_a(idx):
    data = mul([1, 2, 3, 4, 5])
    return data[idx]


def preprocess09_b(idx):
    data = mul([1] * 10)
    return data[idx]


@testbench
def test():
    assert 1 == preprocess09_a(0)
    assert 4 == preprocess09_a(1)
    assert 9 == preprocess09_a(2)

    assert 1 == preprocess09_b(0)

test()
