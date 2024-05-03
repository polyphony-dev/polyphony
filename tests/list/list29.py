from polyphony import testbench


def list29(p, x, y):
    xs = [x]
    ys = [y]
    if p:
        d = xs
    else:
        d = ys
    return d[0]


@testbench
def test():
    assert 1 == list29(True, 1, 2)
    assert 4 == list29(False, 3, 4)
