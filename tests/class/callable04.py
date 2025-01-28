from polyphony import testbench

class C:
    def __init__(self):
        self.count = 0

    def __call__(self, step):
        self.count += step

def fun(c, cnt, step):
    for i in range(cnt):
        c(step)

def call04(cnt, step):
    c = C()
    fun(c, cnt, step)
    return c.count

@testbench
def test():
    assert 10 == call04(10, 1)
    assert 40 == call04(20, 2)
    assert 90 == call04(30, 3)
