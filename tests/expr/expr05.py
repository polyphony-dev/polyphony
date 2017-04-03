from polyphony import testbench


def expr05_a(a):
    return not a


@testbench
def test():
    assert False == expr05_a(True)
    assert True == expr05_a(False)
    assert True is not expr05_a(True)
    assert False is not expr05_a(False)

    assert 0 == expr05_a(1)
    assert 1 == expr05_a(0)
    assert 0 == expr05_a(not 0)
    assert 1 == expr05_a(not 1)

test()
