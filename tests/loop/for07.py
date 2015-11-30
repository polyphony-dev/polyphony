from polyphony import testbench

def for07(x):
    y = x
    z = 0
    for i in range(30):
        for j in range(30):
            z += i * j
    return y + z

@testbench
def test():
    assert 189225 == for07(0)
    assert 189226 == for07(1)
    assert 189227 == for07(2)

test()

