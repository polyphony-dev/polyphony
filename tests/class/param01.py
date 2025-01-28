from polyphony import testbench

class C:
    def __init__(self, x):
        self.x = x

def c_x_mul(cc:object):
    return cc.x * cc.x

def param01(x):
    c = C(x)
    return c_x_mul(c)

@testbench
def test():
    assert 1 == param01(1)
    assert 4 == param01(2)
    assert 9 == param01(3)
