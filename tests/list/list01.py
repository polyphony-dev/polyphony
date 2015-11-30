from polyphony import testbench

def list01(idx1, idx2):
    l = [0, 10, 20, 30]
    return l[idx1] + l[idx2]

@testbench
def test():
    assert 10 == list01(0, 1)
    assert 50 == list01(2, 3)
    assert 30 == list01(3, 0)

test()
