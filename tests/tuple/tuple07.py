from polyphony import testbench

def tuple07(p, x, y, z):
    def f(p, x, y, z):
        if p:
            return x, y
        else:
            return y, z
    a, b = f(p, x, y, z)
    return a + b

@testbench
def test():
    assert 1+2 == tuple07(True, 1, 2, 3)
    assert 2+3 == tuple07(False, 1, 2, 3)    
    assert 4+5 == tuple07(True, 4, 5, 6)
    assert 5+6 == tuple07(False, 4, 5, 6)    
test()
