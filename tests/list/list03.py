from polyphony import testbench

def list03(x, y, z):
    a = [1, 2, 3]

    r0 = x
    r1 = y
    a[r0] = a[r1] + z
    return a[r0]

@testbench
def test():
    assert 4 == list03(0, 1 ,2)
    assert 5 == list03(2, 1 ,3)
test()
