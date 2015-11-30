from polyphony import testbench

#def f():
#    return 0
    
def call03():
    #This must be error in python
    f = 0
    return f() # f() is not callable

@testbench
def test():
    assert 0 == call03()

test()
    
