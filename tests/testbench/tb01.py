from polyphony import testbench

@testbench
def test():
    a = 10
    b = 10
    c = 1
    assert a == 10
    assert 10 == b
    assert a == b
    assert a != c
    print(a)

