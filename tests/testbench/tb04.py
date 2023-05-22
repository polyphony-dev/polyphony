from polyphony import testbench


@testbench
def test():
    data = [0, 1, 2]
    assert 0 == data[0]
    assert 1 == data[1]
    assert 2 == data[2]
    data[0] = 11
    data[1] = 22
    data[2] = 33
    assert 11 == data[0]
    assert 22 == data[1]
    assert 33 == data[2]

test()
