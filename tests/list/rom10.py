from polyphony import testbench

def rom10(x, y, z):
    lst0 = [x, y, z]
    lst1 = [-x, -y, -z]
    lst2 = [0] * 3
    lst2[~x] = -x
    return lst0[0] + lst1[0] + lst1[0]


@testbench
def test():
    assert -1 == rom10(1, 2, 3)


test()
