from polyphony import testbench


def list29(p, xs, ys):
    if p:
        d = xs
    else:
        d = ys
    return d[0]


@testbench
def test():
    assert 1 == list29(True, [1], [2])
    #assert 2 == list29(False, [1], [2])


test()
