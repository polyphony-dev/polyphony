from polyphony import preprocess as pre
from polyphony import testbench


@pre
def tuple_numbers(x):
    return tuple([i for i in range(x)])


@pre
def list_numbers(x):
    return tuple([i for i in range(x)])


def preprocess03_a():
    sum = 0
    data = list_numbers(5 + 5)
    for d in data:
        sum += d
    return sum


def preprocess03_b():
    sum = 0
    data = tuple_numbers(5 + 5)
    for d in data:
        sum += d
    return sum


@testbench
def test():
    assert 45 == preprocess03_a()
    assert 45 == preprocess03_b()


test()
