from polyphony import testbench
def f(l1:list, l2:list):
    return l1[0] + l2[0]

def func09(x):
    a = [x+0]
    b = [x+1]
    c = [x+2]
    t1 = f(a, b)
    t2 = f(b, a)
    return t1 + t2

def func09_b(x):
    a = [x+0]
    b = [x+1]
    c = [x+2]
    t1 = f(a, b)
    t2 = f(a, c)
    return t1 + t2

@testbench
def test():
    assert 2 == func09(0)
    assert 6 == func09(1)
    assert 10 == func09(2)

    assert 3 == func09_b(0)
    assert 7 == func09_b(1)
    assert 11 == func09_b(2)
test()
