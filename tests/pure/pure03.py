from polyphony import pure
from polyphony import testbench


@pure
def tuple_numbers(x):
    return tuple([i for i in range(x)])


@pure
def list_numbers(x):
    return tuple([i for i in range(x)])


def pure03_a():
    sum = 0
    data = list_numbers(5 + 5)
    for d in data:
        sum += d
    return sum


def pure03_b():
    sum = 0
    data = tuple_numbers(5 + 5)
    for d in data:
        sum += d
    return sum


@testbench
def test():
    assert 45 == pure03_a()
    assert 45 == pure03_b()


test()
