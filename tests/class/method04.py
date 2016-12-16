from polyphony import testbench

class C:
    def x(self, x):
        return x

def method04(x):
    c = C()
    return c.x(x)

@testbench
def test():
    assert 1 == method04(1)
    assert 2 == method04(2)
    assert 3 == method04(3)

test()
