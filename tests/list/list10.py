from polyphony import testbench

def list10(x, y):
    data1 = [0, 1, 2]
    data2 = [3, 4, 5]
    if x:
        d1 = data1
        return d1[y]
    else:
        d2 = data2
        return d2[y]

@testbench
def test():
    assert 0 == list10(1, 0)
test()
