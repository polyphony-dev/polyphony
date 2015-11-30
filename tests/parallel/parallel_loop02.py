from polyphony import testbench

def parallel_loop02(x):
    def addloop(init, limit):
        a = 0
        for i in range(init, limit):
            for j in range(init, limit):
                a += j
            print(a)
        return a

    a = addloop(0, x)
    b = addloop(0, x)

    return a + b

@testbench
def test():
    assert 0 == parallel_loop02(0)
    assert 0 == parallel_loop02(1)
    assert 4 == parallel_loop02(2)
    assert 18 == parallel_loop02(3)
    assert 900 == parallel_loop02(10)

test()
