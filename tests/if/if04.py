from polyphony import testbench

def if04(x, y):
    i = 0
    z = x + y
    while True:
        i += 1
        if i > 10: break

        if x == 0:
            if y == 0:
                z = i
        elif x == 1:
            z = 1
        else:
            z = y

    return y + z

@testbench
def test():
    assert 10 == if04(0, 0)
    assert 2 == if04(1, 1)
    assert 4 == if04(2, 2)
