from polyphony import testbench
from polyphony import unroll


def unroll16(start, stop):
    sum = 0
    for i in unroll(range(4)):
        sum += i

    for i in range(10):
        sum += i

    for i in unroll(range(4)):
        sum += i

    return sum


@testbench
def test():
    print(unroll16(0, 10))
    assert 57 == unroll16(0, 10)


test()