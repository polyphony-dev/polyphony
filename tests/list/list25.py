from polyphony import testbench

def list25(x):
    def f(x:list, y:list, i):
        if i:
            z = x
        else:
            z = y
        return len(z)
    data0 = [x]
    data1 = [x, x]
    return f(data0, data1, x)

@testbench
def test():
    assert 2 == list25(0)
    assert 1 == list25(1)
test()
