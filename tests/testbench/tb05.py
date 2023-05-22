from polyphony import testbench


@testbench
def test():
    rom = (0, 1, 2)
    assert 0 == rom[0]
    assert 1 == rom[1]
    assert 2 == rom[2]

test()
