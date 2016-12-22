from polyphony import testbench

class C:
    def __init__(self, x):
        self.x = x

    def __call__(self):
        return self.x

class D:
    def __init__(self, c):
        self.c = c

    def __call__(self):
        return self.c


def call05(x):
    d = D(C(x))
    c = d()
    return c()

@testbench
def test():
    assert 1 == call05(1)
    assert 2 == call05(2)
    assert 3 == call05(3)

test()
