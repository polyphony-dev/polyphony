from polyphony import testbench

def func05(x):
    def f(a):
        return a * 2

    a = [x+1, x+2]
    print(a[0])
    ret = f(a[0])
    return ret

@testbench
def test():
    assert 2 == func05(0)
    assert 4 == func05(1)
    assert 6 == func05(2)

test()
