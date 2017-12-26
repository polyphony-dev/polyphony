from polyphony import testbench
from polyphony import unroll


def unroll15_a(start, stop):
    sum = 0
    for i in unroll(range(start, stop), 4):
        sum += i
    return sum


def unroll15_b(start, stop):
    sum = 0
    for i in unroll(range(start, stop), 5):
        sum += i
    return sum


@testbench
def test():
    assert 0 == unroll15_a(0, 0)
    assert 45 == unroll15_a(0, 10)
    assert 35 == unroll15_a(5, 10)

    assert 0 == unroll15_b(0, 0)
    assert 45 == unroll15_b(0, 10)
    assert 35 == unroll15_b(5, 10)


test()
