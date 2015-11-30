from polyphony import testbench

def list08(x, y, z):
    index = [x, y, z]
    data = [2, 3, 4]

    a = data[index[0]]
    b = data[index[1]]
    c = data[index[2]]
    return a + b * c

@testbench
def test():
    assert 14 == list08(0, 1, 2)
    assert 11 == list08(1, 2, 0)
    assert 10 == list08(2, 0, 1)
test()
