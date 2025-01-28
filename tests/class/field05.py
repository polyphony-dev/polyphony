from polyphony import testbench

class C:
    def __init__(self, x):
        self.x = x

def field05(x):
    c = C(x)
    c = C(x+1)
    return c.x

@testbench
def test():
    assert 2 == field05(1)
    assert 3 == field05(2)
    assert 4 == field05(3)
