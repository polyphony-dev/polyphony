from polyphony import testbench

def func07(x):
    def f(a:list, idx:int):
        a[idx] *= 2
        b = a[idx]
        return b

    y = [1,2,3]
    z = [2,3,4]
    f(y, 0)
    f(z, 1)
    f(y, 2)
    return y[x]

@testbench
def test():
    assert 2 == func07(0)
    assert 2 == func07(1)
    assert 6 == func07(2)
