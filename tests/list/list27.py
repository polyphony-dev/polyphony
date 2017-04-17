from polyphony import testbench


def list27(x):
    mem = [x] * 4096
    return mem[0]


@testbench
def test():
    assert 10 == list27(10)


test()
