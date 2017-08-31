from polyphony import testbench


def if19(x):
    if x < 10:
        assert False
    elif x < 20:
        assert False
    elif x < 30:
        assert False
    else:
        pass
    return x


@testbench
def test():
    assert 30 == if19(30)


test()
