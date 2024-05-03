from polyphony import testbench

def f(d:list):
    return d[0]

def g(d:list):
    return f(d)

def special03(x):
    data1 = [1, 2, 3]
    data2 = [4, 5, 6]

    x = g(data1)
    y = g(data2)
    return x + y

@testbench
def test():
    assert 5 == special03(1)
