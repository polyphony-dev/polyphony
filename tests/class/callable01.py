from polyphony import testbench

class C:
    def __call__(self, x):
        return x

def call01(x):
    c = C()
    return c(x)

@testbench
def test():
    assert 1 == call01(1)
    assert 2 == call01(2)
    assert 3 == call01(3)

test()
