from polyphony import testbench
from polyphony import unroll


def unroll05_a():
    xs = [1, 2, 3, 4]
    sum = 0
    for i in unroll(range(2, 4)):
        sum += xs[i]
    return sum


def unroll05_b():
    xs = [10, 20, 30, 40]
    sum = 0
    for i in unroll(range(3, 4)):
        sum += xs[i]
    return sum


def unroll05_c():
    xs = [10, 20, 30, 40]
    sum = 0
    for k in range(4, 4):
        for i in unroll(range(4, 4)):
            sum += xs[i]
    return sum


@testbench
def test():
    assert 7 == unroll05_a()
    assert 40 == unroll05_b()
    assert 0 == unroll05_c()
