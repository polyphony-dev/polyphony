from polyphony import testbench

def for08(x):
    y = x
    z = 0
    for i in range(10+x):
        for j in range(10):
            for k in range(10):
                z += i + j + k
    return y + z

@testbench
def test():
    assert 13500 == for08(0)
    assert 15401 == for08(1)
    assert 17402 == for08(2)

test()
