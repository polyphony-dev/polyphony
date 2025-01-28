from polyphony import testbench


def rom07(d):
    data = [d] * 8
    return data[0]


@testbench
def test():
    assert 1 == rom07(1)
    assert 2 == rom07(2)
    assert 3 == rom07(3)
