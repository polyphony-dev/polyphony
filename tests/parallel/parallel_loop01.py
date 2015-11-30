from polyphony import testbench


def parallel_loop01(x):
    def addloop(init, limit, step):
        a = 0
        for i in range(init, limit, step):
            a += i
            print(i)
        return a

    a = addloop(0,   x,   1)
    b = addloop(x,   x*2, 1)
    c = addloop(x*2, x*3, 1)
    return a + b + c

@testbench
def test():
    assert 0 == parallel_loop01(0)
    assert 1+2+3+4+5 == parallel_loop01(2)
    assert 1+2+3+4+5+6+7+8 == parallel_loop01(3)
    assert 1+2+3+4+5+6+7+8+9+10+11 == parallel_loop01(4)
    assert 1+2+3+4+5+6+7+8+9+10+11+12+13+14 == parallel_loop01(5)

test()
