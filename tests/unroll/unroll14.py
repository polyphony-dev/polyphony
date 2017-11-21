from polyphony import testbench
from polyphony import unroll


def unroll14_a(stop):
    sum = 0
    for i in unroll(range(stop), 4):
        sum += i
    return sum


def unroll14_b(stop):
    sum = 0
    for i in unroll(range(stop), 5):
        sum += i
    return sum


@testbench
def test():
    assert 0 == unroll14_a(0)
    assert 0 == unroll14_a(1)
    assert 1 == unroll14_a(2)
    assert 6 == unroll14_a(4)
    assert 45 == unroll14_a(10)

    assert 0 == unroll14_b(0)
    assert 0 == unroll14_b(1)
    assert 1 == unroll14_b(2)
    assert 6 == unroll14_b(4)
    assert 45 == unroll14_b(10)


test()
