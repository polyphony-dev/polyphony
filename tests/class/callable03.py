from polyphony import testbench

class C:
    def __init__(self):
        self.count = 0

    def __call__(self):
        self.count += 1

def fun(c, cnt):
    for i in range(cnt):
        c()

def call03(cnt):
    c = C()
    fun(c, cnt)
    return c.count

@testbench
def test():
    assert 10 == call03(10)
    assert 20 == call03(20)
    assert 30 == call03(30)

test()
