from polyphony import testbench


def if29(p0, p1, p2):
    x = 0
    if p0 == 0:
        pass
    elif p0 == 1:
        if p1 == 0:
            if p2 == 0:
                x = 10
        elif p1 == 1:
            pass
        elif p1 == 2:
            pass
        else:
            return -1
            #x = -1
    return x


@testbench
def test():
    assert 0 == if29(0, 0, 0)
    assert 10 == if29(1, 0, 0)
    assert 0 == if29(1, 0, 1)
    assert 0 == if29(1, 1, 0)
    assert 0 == if29(1, 2, 0)
    assert -1 == if29(1, 3, 0)
    assert 0 == if29(2, 3, 0)
