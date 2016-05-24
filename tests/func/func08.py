from polyphony import testbench

def func08(x):
    def f(a:list, idx):
        a[idx] *= 2
    
    y = [1,2,3]
    f(y, x) #must show the error message
    return y[x]

@testbench
def test():
    assert 2 == func08(0)
    assert 4 == func08(1)
    assert 6 == func08(2)    

test()
