from polyphony import testbench

def f():
    return 0

def call02():
    return f()

@testbench
def test():
    assert 0 == call02()
