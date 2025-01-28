from polyphony import testbench


def for18(stop, p):
    ss = 1
    s = 0
    if p:
        v = 0
        for i in range(10):
            v += 1
    while True:
        if p == 0:
            pass
        elif p == 1:
            ss += 1
        elif p == 2:
            ss += 2
        else:
            continue
        s += ss
        if s > stop:
            break
    return s


@testbench
def test():
    assert 11 == for18(10, 0)
    assert 14 == for18(10, 1)
    assert 15 == for18(10, 2)
