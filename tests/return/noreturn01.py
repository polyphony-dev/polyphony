from polyphony import testbench


def fun(data):
    while True:
        for i in range(4):
            data[i] = i
        break


def noreturn01(data):
    fun(data)


@testbench
def test():
    data = [0] * 10
    noreturn01(data)
    assert data[0] == 0
    assert data[1] == 1
    assert data[2] == 2
    assert data[3] == 3
    assert data[4] == 0


test()
