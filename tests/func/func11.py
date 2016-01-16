from polyphony import testbench
def f(l1:list, l2:list):
    return l1[0] + l2[0]

def func11(a:list, b:list):
    t1 = f(a, b)
    t2 = f(b, a)
    return t1 + t2

@testbench
def test():
    a = [1]
    b = [2]
    assert 6 == func11(a, b)
test()
