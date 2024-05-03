from polyphony import testbench

def f(a:list, idx):
    a[idx] *= 2

def func08(x):
    y = [1,2,3]
    f(y, x)
    return y[x]

def func08_b(x):
    y = [4,5,6]
    f(y, x)
    return y[x]

@testbench
def test():
    assert 2 == func08(0)
    assert 4 == func08(1)
    assert 6 == func08(2)

    assert 8 == func08_b(0)
    assert 10 == func08_b(1)
    assert 12 == func08_b(2)
