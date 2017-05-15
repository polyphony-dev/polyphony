from polyphony import testbench


def rom07(data):
    return data[0]


@testbench
def test():
    assert 1 == rom07([1] * 8)
    assert 2 == rom07([2] * 8)
    assert 3 == rom07([3] * 8)


test()
