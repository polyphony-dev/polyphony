from polyphony import testbench

def for09(x):
    y = x
    z = 0
    for i in range(10+x):
        if i > 5:
            z += 1
            if i > 6:
                z += 1
                if i > 7:
                    z += 1
                    if i > 8:
                        z += 1

    return y + z

@testbench
def test():
    assert 10 == for09(0)
    assert 35 == for09(5)
    assert 60 == for09(10)
test()
