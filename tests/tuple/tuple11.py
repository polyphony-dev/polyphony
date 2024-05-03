from polyphony import testbench


def sum(ts:tuple):
    def sub_sum(ts:tuple):
        def sub_sub_sum(ts:tuple):
            s = 0
            for t in ts:
                s += t
            return s
        return sub_sub_sum(ts)
    return sub_sum(ts)


def tuple11(x):
    data1 = (x, 1, 2)
    data2 = (x, 1, 2, 3, 4, 5)
    s1 = sum(data1)
    s2 = sum(data2)
    return s1 + s2 + x


@testbench
def test():
    assert 18 == tuple11(0)
    assert 21 == tuple11(1)
    assert 24 == tuple11(2)
