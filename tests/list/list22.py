from polyphony import testbench

def list22(x, y):
    data0 = [x+1]
    data1 = [x]
    if x:
        a = data0
        b = data1
    else:
        a = data1
        b = data0
    if y:
        c = a
    else:
        c = b
    return c[0]

@testbench
def test():
    assert 1 == list22(0, 0)
    assert 1 == list22(1, 0)
    assert 0 == list22(0, 1)
    assert 2 == list22(1, 1)    
test()
