#The step value must be a constant
from polyphony import testbench
from polyphony import unroll


def unroll02(start, stop, step):
    sum = 0
    for i in unroll(range(start, stop, step), 5):
        sum += i
    return sum


@testbench
def test():
    assert 35 == unroll02(5, 10, 1)


test()
