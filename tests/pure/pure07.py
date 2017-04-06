from polyphony import pure
from polyphony import testbench


@pure
def f(x):
    def ff(x):
        return sum([i for i in range(x)])
    return ff(x)


value = f(100)


@testbench
def test():
    assert 4950 == value


test()
