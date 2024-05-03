from polyphony import testbench

def if05(x, y):
    z = 0
    if x > 0:
        if y > 0:
            z = 3
    z += 1

    if x > 5:
        if y > 5:
            z = 5
    z += 1

    return y + z

@testbench
def test():
    assert 2 == if05(0, 0)
    assert 6 == if05(1, 1)
    assert 16 == if05(10, 10)
