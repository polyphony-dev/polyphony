from polyphony import testbench


def expr05(a):
    return not a


@testbench
def test():
    assert False == expr05(True)
    assert True == expr05(False)
    assert True is not expr05(True)
    assert False is not expr05(False)

    assert 0 == expr05(1)
    assert 1 == expr05(0)
    assert 0 == expr05(not 0)
    assert 1 == expr05(not 1)
