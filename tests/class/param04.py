from polyphony import testbench

class C:
    def __init__(self, x):
        self.x = x

    def get_x(self):
        return self.x

class D:
    def __init__(self):
        pass

    def get_x(self, c):
        return c.x + c.get_x()

def param04(x):
    c = C(x)
    d = D()
    return d.get_x(c)

@testbench
def test():
    assert 2 == param04(1)
    assert 4 == param04(2)
    assert 6 == param04(3)

test()
