from polyphony import testbench

class D:
    def __init__(self, x):
        self.x = x

    def get_x(self):
        return self.x

class C:
    def __init__(self, x):
        self.d = D(x)

    def get_x(self):
        return self.d.get_x()

def composition04(x):
    c = C(x)
    a = c.get_x() + c.get_x()
    return a

@testbench
def test():
    assert 2 == composition04(1)
    assert 4 == composition04(2)
    assert -6 == composition04(-3)
