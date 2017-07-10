from polyphony import testbench


def if22(data, p):
    if p == 0:
        data[0] = data[0] * data[1]
        return data[0]
    elif p == 1:
        data[1] = data[1] * data[2]
        return data[1]
    elif p == 2:
        data[2] = data[2] * data[3]
        return data[2]
    return 0


@testbench
def test():
    data = [1, 2, 3, 4]
    assert 2 == if22(data, 0)
    assert 6 == if22(data, 1)
    assert 12 == if22(data, 2)
    assert 0 == if22(data, 3)


test()
