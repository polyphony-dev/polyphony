from polyphony import testbench

def if03(x, y):
    if x == 0:
        z = y
        y *= 2
        y *= 3
        if y > 10:
            y *= 4
        else:
            y *= 5
        y *= 6
    else:
        z = y

    return y + z

@testbench
def test():
    assert 181 == if03(0, 1)
    assert 2 == if03(1, 1)
    assert 290 == if03(0, 2)
