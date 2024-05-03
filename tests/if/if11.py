from polyphony import testbench

def if11(x):
    if True:
        y = 3
        if x == 1:
            y = 1
        elif x == 2:
            y = 2
    return y

@testbench
def test():
    assert 3 == if11(0)
    assert 1 == if11(1)
    assert 2 == if11(2)
    assert 3 == if11(3)
    assert 3 == if11(4)
