from polyphony import testbench

class C:
    def __init__(self, x):
        self.t = (x,)

def field06(x):
    c = C(x)
    return c.t[0]

@testbench
def test():
    assert 1 == field06(1)
    assert 2 == field06(2)
    assert 3 == field06(3)

test()
