from polyphony import testbench
from polyphony import unroll


def unroll09_a(xs:list):
    sum = 0
    for i in unroll(range(10), 4):
        sum += xs[i]
    return sum


def unroll09_b(xs:list):
    sum = 0
    for i in unroll(range(10), 3):
        sum += xs[i]
    return sum


def unroll09_c(xs:list):
    sum = 0
    for i in unroll(range(10), 6):
        sum += xs[i]
    return sum


def unroll09():
    assert 55 == unroll09_a([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    assert 55 == unroll09_b([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    assert 55 == unroll09_c([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])


@testbench
def test():
    unroll09()

test()
