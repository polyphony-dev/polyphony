from polyphony import testbench

def func01(x):
    def inner(y):
        return y + 1
    return inner(x)

@testbench
def test():
    assert 1 == func01(0)
    assert 2 == func01(1)
    assert 3 == func01(2)
