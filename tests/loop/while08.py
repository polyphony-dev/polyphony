from polyphony import testbench


def while08(n):
    x = 1
    y = 2
    while True:
        #z = y
        y = x
        x = 5
        n -= 1
        if n < 0:
            break
    print(x, y)
    return x + y


@testbench
def test():
    assert 6 == while08(0)
    assert 10 == while08(1)


test()
