from polyphony import testbench


def for15(x):
    sum = 0
    for i in range(0, x):
        sum += i
        x = 5
    return sum


@testbench
def test():
    assert 0 == for15(0)
    assert 6 == for15(4)
    assert 10 == for15(5)
