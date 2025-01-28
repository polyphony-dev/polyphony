from polyphony import testbench

data = (2, 4, 6, 8, 10)
index = (4, 3, 2, 1, 0)
def idx(i):
    return index[i]
def rom06(i):
    return data[idx(i)]

@testbench
def test():
    assert 10 == rom06(0)
    assert 8 == rom06(1)
    assert 6 == rom06(2)
