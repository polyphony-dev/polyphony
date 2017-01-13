from polyphony import testbench

def tuple01(idx1, idx2):
    tup = (0, 10, 20, 30)
    return tup[idx1] + tup[idx2]

@testbench
def test():
    assert 10 == tuple01(0, 1)
    assert 50 == tuple01(2, 3)
    assert 30 == tuple01(3, 0)

test()
