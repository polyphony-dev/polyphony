from polyphony import testbench

def return05(x):
    if x == 0: return 0
    if x == 1: return 1
    if x == 2: return 2
    if x == 3: return 3
    return -1

@testbench
def test():
    assert 0 == return05(0)
    assert 1 == return05(1)
    assert 2 == return05(2)
    assert 3 == return05(3)
    assert -1 == return05(4)

test()
