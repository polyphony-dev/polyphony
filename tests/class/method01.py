from polyphony import testbench

class C:
    def __init__(self, x):
        self.x = x

    def get_x(self):
        return self.x

def method01(x):
    c = C(x)
    return c.get_x() + c.get_x()

@testbench
def test():
    assert 2 == method01(1)
    assert 4 == method01(2)
    assert 6 == method01(3)

test()
