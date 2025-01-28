from polyphony import testbench

def if12(x, y, z):
    if x == 0:
        z = 0
    elif x == 1:
        if y == 0:
            z = 0
        elif y == 1:
            z = 1
        else:
            z = 2
        z = 1
    else:
        z = 2

    return z

@testbench
def test():
    assert 0 == if12(0, 1, 2)
    assert 2 == if12(2, 0, 1)
    assert 1 == if12(1, 2, 0)
