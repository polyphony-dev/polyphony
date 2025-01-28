from polyphony import testbench

def special01(x):
    def inner(a, b, c):
        return a + b + c

    return inner(0, x, 0) + inner(1, 0, 0)

@testbench
def test():
    assert 1 == special01(0)
    assert 2 == special01(1)
    assert 3 == special01(2)
