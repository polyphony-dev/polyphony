from polyphony import testbench

def f(l:list, i):
    assert i >= 0 and i < 3
    return l[i]

@testbench
def test():
    data = [0, 1, 2]
    assert 0 == f(data, 0)
    assert 1 == f(data, 1)
    assert 2 == f(data, 2)
    data[0] = 11
    data[1] = 22
    data[2] = 33
    assert 11 == f(data, 0)
    assert 22 == f(data, 1)
    assert 33 == f(data, 2)
