from polyphony import testbench

def func06(x):
    def f(a:list, idx:int):
        a[idx] *= 2
        return a[idx]

    y = [1,2,3]
    z = [2,3,4]
    f(y, 0)
    f(y, 1)
    f(y, 2)
    return y[x]

@testbench
def test():
    assert 2 == func06(0)
    assert 4 == func06(1)
    assert 6 == func06(2)
