from polyphony import testbench

def f(l1:list, l2:list):
    return l1[0] + l2[0]


def func11():
    a = [1]
    b = [2]
    t1 = f(a, b)
    t2 = f(b, a)
    return t1 + t2


@testbench
def test():
    assert 6 == func11()
test()
