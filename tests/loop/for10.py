from polyphony import testbench

def for10(x):
    y = x
    z = 0
    for i in range(10+x):
        if i > 5:
            z += 1
        else:
            if i > 4:
                z += 1
            else:
                if i > 3:
                    z += 1
                else:
                    if i > 2:
                        z += 1

    return y + z

@testbench
def test():
    assert 7 == for10(0)
    assert 17 == for10(5)
    assert 27 == for10(10)
test()
