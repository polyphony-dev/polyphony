from polyphony import testbench
from polyphony import unroll


def unroll05_a(xs):
    sum = 0
    for i in unroll(range(2, 4)):
        sum += xs[i]
    return sum


def unroll05_b(xs):
    sum = 0
    for i in unroll(range(3, 4)):
        sum += xs[i]
    return sum


def unroll05_c(xs):
    sum = 0
    for k in range(4, 4):
        for i in unroll(range(4, 4)):
            sum += xs[i]
    return sum


@testbench
def test():
    assert 7 == unroll05_a([1, 2, 3, 4])
    assert 40 == unroll05_b([10, 20, 30, 40])
    assert 0 == unroll05_c([10, 20, 30, 40])


test()
