from polyphony import testbench

def f():
    return 0
    
def call01():
    def f():
        return 1
    return f()

@testbench
def test():
    assert 1 == call01()

test()
    
