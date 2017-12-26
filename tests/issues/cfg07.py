from polyphony import testbench


def cfg07(p, v):
    if p == 0:
        for i in range(4):
            v[0] += 1
    elif p == 1:
        for i in range(4):
            v[0] += 2
    elif p == 2:
        v[0] += 3
    else:
        assert p == 3
        v[0] += 1
    return v[0]

@testbench
def test():
    assert 5 == cfg07(0, [1])
    assert 9 == cfg07(1, [1])
    assert 4 == cfg07(2, [1])
    assert 3 == cfg07(3, [2])


test()
