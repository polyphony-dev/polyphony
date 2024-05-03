from polyphony import testbench


def if17(x, y):
    while True:
        if x == 0:
            y = 10
        elif x == 1:
            pass
        elif x == 2:
            pass

        if y == 0:
            y += 1
        else:
            if y > 1:
                y += 1
            elif y > 2:
                y += 1
            else:
                pass
            pass
        if x != 0:
            break
        x += 1
    print(x, y)
    return x + y


@testbench
def test():
    assert 13 == if17(0, 0)
    assert 2 == if17(1, 1)
    assert 5 == if17(2, 2)
