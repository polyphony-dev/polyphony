from polyphony import testbench

class C:
    def __init__(self, x):
        self.x = x * x

    def calc(self, x):
        return self.x * x

def method05(x):
    return C(x).calc(x)

@testbench
def test():
    assert 1 == method05(1)
    assert 8 == method05(2)
    assert 27 == method05(3)

test()
