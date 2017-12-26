from polyphony import testbench


SIZE1 = 2
SIZE2 = 10
SIZE3 = 20


def init01():
    mem = [0] * SIZE1 * SIZE2 * SIZE3
    for i in range(SIZE1 * SIZE2 * SIZE3):
        mem[i] = i
    s = 0
    for m in mem:
        s += m
    return s


@testbench
def test():
    assert 79800 == init01()


test()
