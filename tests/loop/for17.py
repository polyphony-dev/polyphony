from polyphony import testbench


def for17(stop, p):
    s = 0
    ss = 1
    for i in range(stop):
        if p == 0:
            pass
        elif p == 1:
            ss += 1
        elif p == 2:
            ss += 2
        else:
            continue
        s += ss
    return s


@testbench
def test():
    assert 65 == for17(10, 1)
