from polyphony import testbench

def rom10(x, y, z):
    lst0 = [x, y, z]
    lst1 = [-x, -y, -z]
    lst2 = [0] * 4
    v = ~x
    print(v, ~v)
    lst2[0] = 1
    lst2[1] = 2
    lst2[2] = 3
    lst2[v] = 10
    print(lst2[0], lst2[1], lst2[2], lst2[3])
    return lst0[0] + lst1[0] + lst1[0]


@testbench
def test():
    assert -1 == rom10(1, 2, 3)
