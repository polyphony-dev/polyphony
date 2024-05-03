from polyphony import testbench

def f(x):
    return x

@testbench
def test():
    a = 10
    assert a == f(a)
    assert f(a) == a
    assert f(a) == f(a)
    print(f(a))
