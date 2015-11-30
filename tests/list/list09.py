from polyphony import testbench

def list09(x):
    data = [0, 1, 2]
    def f(d:list):
        def swap(dd:list, i, j):
            t = dd[i]
            dd[i] = dd[j]
            dd[j] = t
        swap(d, 0, 1)
        swap(d, 1, 2)
        
    f(data)
    return data[x]

@testbench
def test():
    assert 1 == list09(0)
    assert 2 == list09(1)
    assert 0 == list09(2)
test()
