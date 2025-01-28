from polyphony import testbench
from polyphony import unroll


def unroll07_a(xs:list):
    sum = 0
    for i in unroll(range(0, 4, 2)):
        sum += xs[i]
    return sum


def unroll07_b(xs:list):
    sum = 0
    for i in unroll(range(1, 9, 2)):
        sum += xs[i]
    return sum


def unroll07_c(xs:list):
    sum = 0
    for i in unroll(range(1, 12, 2)):
        sum += xs[i]
    return sum


def unroll07():
    assert 4 == unroll07_a([1, 2, 3, 4])
    assert 20 == unroll07_b([1, 2, 3, 4, 5, 6, 7, 8])
    assert 42 == unroll07_c([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])


@testbench
def test():
    unroll07()
