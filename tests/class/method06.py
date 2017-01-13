from polyphony import testbench

class C:
    def __init__(self, x):
        self.x = x * x

    def calc(self, x):
        for i in range(x):
            self.x += 1
        return self.x

def method06(x):
    return C(x).calc(x)

@testbench
def test():
    assert 2 == method06(1)
    assert 6 == method06(2)
    assert 12 == method06(3)

test()
