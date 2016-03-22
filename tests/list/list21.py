from polyphony import testbench

def list21(x):
    data0 = [x, x, x]
    data1 = [x]
    if x:
        d = data0
    else:
        d = data1
    return len(d)

@testbench
def test():
    assert 1 == list21(0)
    assert 3 == list21(1)
test()
