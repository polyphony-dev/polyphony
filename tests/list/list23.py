from polyphony import testbench

def list23(x):
    def f(x:list):
        def ff(x:list):
            return x[0]
        return ff(x)
    data0 = [x+1]
    data1 = [x]
    if x:
        d = data0
    else:
        d = data1
    return f(d)

@testbench
def test():
    assert 0 == list23(0)
    assert 2 == list23(1)
