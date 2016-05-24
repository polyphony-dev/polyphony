from polyphony import testbench

def aliasing_list(x):
    def f(a:list, b:list):
        a[0] *= 2
        b[0] *= 2
    
    y = [1,2,3]
    f(y, y) #must show the error message
    return y[x]

@testbench
def test():
    assert 4 == aliasing_list(0)

test()
