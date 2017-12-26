from polyphony import testbench


def return_tuple(x, y):
    return (x, y)


def tuple10(x, y):
    a, b = return_tuple(x, y)
    return a + b


@testbench
def test():
    assert 1 + 2 == tuple10(1, 2)
    assert 4 + 5 == tuple10(4, 5)


test()
