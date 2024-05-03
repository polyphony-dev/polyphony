from polyphony import testbench


def f(a):
    a += 1


def inline():
    a = 0
    f(a)
    return a

@testbench
def test():
    assert 0 == inline()
