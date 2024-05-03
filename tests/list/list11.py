from polyphony import testbench


def sum(l1:list):
    def sum_x(l2:list):
        def sum_y(l2:list):
            s = 0
            for l in l2:
                s += l
            return s
        return sum_y(l2)
    return sum_x(l1)

def list11(x):
    data1 = [x, 1, 2]
    data2 = [x, 1, 2, 3, 4, 5]
    s1 = sum(data1)
    s2 = sum(data2)
    return s1 + s2 + x

@testbench
def test():
    assert 18 == list11(0)
    assert 21 == list11(1)
    assert 24 == list11(2)
