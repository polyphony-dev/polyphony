from polyphony import testbench

def list05(x):
    a = [1,2,3,4]*100

    def f(x:list):
        for i in range(0, 4):
            x[i] *= 2

    def g(x:list):
        for i in range(0, 4):
            x[i] += 1

    f(a)
    g(a)
    return a[x]

@testbench
def test():
    assert 3 == list05(0)
    assert 5 == list05(1)
    assert 7 == list05(2)
    assert 9 == list05(3)
