from polyphony import testbench

def func10(x, y, z):
    def inner(a):
        return a

    data0 = inner(y)
    data1 = inner(z)
    if x:
        d = data0
    else:
        d = data1
    return d

@testbench
def test():
    assert 3 == func10(0, 2, 3)
    assert 2 == func10(1, 2, 3)    

test()
