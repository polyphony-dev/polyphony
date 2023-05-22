from polyphony import testbench
from polyphony import unroll


def unroll10_a(xs:list):
    sum = 0
    for i in unroll(range(0, 10, 2), 4):
        sum += xs[i]
    return sum


def unroll10_b(xs:list):
    sum = 0
    for i in unroll(range(1, 10, 2), 4):
        sum += xs[i]
    return sum


def unroll10_c(xs:list):
    sum = 0
    for i in unroll(range(1, 10, 2), 3):
        sum += xs[i]
    return sum


def unroll10():
    assert 25 == unroll10_a([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])
    assert 30 == unroll10_b([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])
    assert 30 == unroll10_c([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])


@testbench
def test():
    unroll10()

test()
