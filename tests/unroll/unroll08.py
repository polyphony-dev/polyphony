from polyphony import testbench
from polyphony import unroll


def unroll08_a(xs:list):
    sum = 0
    for i in unroll(range(0, 4, 2), 2):
        sum += xs[i]
    return sum


def unroll08_b(xs:list):
    sum = 0
    for i in unroll(range(1, 9, 2), 2):
        sum += xs[i]
    return sum


def unroll08_c(xs:list):
    sum = 0
    for i in unroll(range(1, 12, 2), 3):
        sum += xs[i]
    return sum


@testbench
def test():
    assert 4 == unroll08_a([1, 2, 3, 4])
    assert 20 == unroll08_b([1, 2, 3, 4, 5, 6, 7, 8])
    assert 42 == unroll08_c([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])


test()
