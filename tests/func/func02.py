from polyphony import testbench

def func02(x):
    def f(a):
        return a
    return f(x) + f(x+1)

@testbench
def test():
    assert 1 == func02(0)
    assert 3 == func02(1)
    assert 5 == func02(2)

test()

