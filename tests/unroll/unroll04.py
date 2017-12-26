from polyphony import testbench
from polyphony import unroll


def unroll04_a(xs:list):
    sum = 0
    for x in unroll(xs, 4):
        sum += x
    return sum


def unroll04_b(xs:list):
    sum = 0
    for x in unroll(xs, 2):
        sum += x
    return sum


@testbench
def test():
    xs = [10, 20, 30, 40]
    assert 100 == unroll04_a(xs)
    assert 100 == unroll04_b(xs)


test()
