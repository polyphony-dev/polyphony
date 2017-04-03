from polyphony import testbench

def if10(x, y, z):
    if x == 0:
        if y == 0:
            z = 0
        elif y == 1:
            z = 1
        else:
            z = 2
    elif x == 1:
        z = 1
    else:
        z = 2

    return z

@testbench
def test():
    assert 0 == if10(0, 0, 1)
    assert 1 == if10(0, 1, 0)
    assert 2 == if10(0, 2, 0)
    assert 1 == if10(1, 0, 0)
    assert 2 == if10(2, 0, 0)
    
test()
