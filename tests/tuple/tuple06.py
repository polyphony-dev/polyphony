from polyphony import testbench

def tuple06(x, i):
    def f(t, i):
        return t[i]
    return f((x, x+1, x+2), i)

@testbench
def test():
    assert 11 == tuple06(10, 1)
    assert 12 == tuple06(10, 2)
