from polyphony import testbench
from polyphony import unroll


def f(a):
    if (a < 0):
        return -a
    else:
        return a

def unroll17():
    sum = 0
    for i in unroll(range(-10, 10)):
        sum += f(i)

    return sum


@testbench
def test():
    assert 100 == unroll17()


test()