#@pure function must be in the global scope
from polyphony import pure
from polyphony import testbench


def f(x):
    @pure
    def ff(x):
        return sum([i for i in range(x)])
    return ff(x)


@testbench
def test():
    assert 4950 == f(100)


test()
