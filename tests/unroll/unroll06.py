from polyphony import testbench
from polyphony import unroll


def unroll06_a(xs:list):
    sum = 0
    for i in unroll(range(2, 4), 2):
        sum += xs[i]
    return sum


def unroll06_b(xs:list):
    sum = 0
    for i in unroll(range(2, 10), 4):
        sum += xs[i]
    return sum


def unroll06_c(xs:list):
    sum = 0
    for i in unroll(range(2, 10), 2):
        sum += xs[i]
    return sum


def unroll06():
    assert 7 == unroll06_a([1, 2, 3, 4])
    assert 520 == unroll06_b([10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
    assert 520 == unroll06_c([10, 20, 30, 40, 50, 60, 70, 80, 90, 100])


@testbench
def test():
    unroll06()
