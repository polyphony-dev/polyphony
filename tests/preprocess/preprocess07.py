from polyphony import preprocess as pre
from polyphony import testbench


@pre
def f(x):
    def ff(x):
        return sum([i for i in range(x)])
    return ff(x)


value = f(100)


@testbench
def test():
    assert 4950 == value


test()
