from polyphony import testbench


@testbench
def test():
    rom = (0, 1, 2)
    assert 1 == rom[0] + rom[1]
    assert 3 == rom[1] + rom[2]
    assert 2 == rom[2] + rom[0]
