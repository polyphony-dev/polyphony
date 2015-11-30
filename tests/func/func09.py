from polyphony import testbench

def func09():
    def f(l1:list, l2:list):
        return l1[0] + l2[0]
    
    a = [0]
    b = [1]
    c = [2]
    #f(a,b) and f(a,c) are must be different instances
    t1 = f(a, b)
    t2 = f(a, c)
    return t1 + t2

@testbench
def test():
    assert 3 == func09()

test()
