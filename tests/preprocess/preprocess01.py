from polyphony import preprocess as pre
from polyphony import testbench


@pre
def f(x):
    def ff(x):
        return sum([i for i in range(x)])
    return ff(x)


@testbench
def test():
    assert 4950 == f(100)
    assert 4950 + 4950 == f(100) + f(100)
    print(f(1000))


test()
