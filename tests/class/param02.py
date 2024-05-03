from polyphony import testbench

class C:
    def __init__(self, x):
        self.x = x

    def get_x(self):
        return self.x

def c_get_x_mul(cc:object):
    return cc.get_x() * cc.get_x()

def param02(x):
    c = C(x)
    return c_get_x_mul(c)

@testbench
def test():
    assert 1 == param02(1)
    assert 4 == param02(2)
    assert 9 == param02(3)
