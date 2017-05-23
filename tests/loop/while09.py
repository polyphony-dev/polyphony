from polyphony import testbench


def while09(n):
    x = 1
    while True:
        y = x
        x = 2
        n -= 1
        if n < 0:
            break

    return y


@testbench
def test():
    assert 1 == while09(0)
    assert 2 == while09(1)


test()
