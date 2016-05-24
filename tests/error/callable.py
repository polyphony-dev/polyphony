from polyphony import testbench

#def f():
#    return 0
    
def callable():
    #This must be error in python
    f = 0
    return f() # f() is not callable

@testbench
def test():
    assert 0 == callable()

test()
    
