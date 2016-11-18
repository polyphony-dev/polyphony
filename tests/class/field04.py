from polyphony import testbench

class C:
    def __init__(self, x):
        self.lst = [x]
        self.x = x

def field04(x):
    c = C(x)
    c.lst[0] = c.lst[0]
    return c.lst[0]

@testbench
def test():
    assert 1 == field04(1)
    assert 2 == field04(2)
    assert 3 == field04(3)

test()
