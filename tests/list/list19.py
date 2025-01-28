from polyphony import testbench


def sum(l1:list):
    s = 0
    for l in l1:
        s += l
    return s

def list19(x):
    data1 = [x, 1, 2]
    data2 = [x, 1, 2, 3, 4, 5]
    s1 = sum(data1)
    s2 = sum(data2)
    return s1 + s2 + x

@testbench
def test():
    assert 18 == list19(0)
