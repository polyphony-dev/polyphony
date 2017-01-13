from polyphony import testbench

class C:
    def __init__(self):
        self.count = 0

    def __call__(self):
        self.count += 1

def call02(cnt):
    c = C()
    for i in range(cnt):
        c()
    return c.count

@testbench
def test():
    assert 10 == call02(10)
    assert 20 == call02(20)
    assert 30 == call02(30)

test()
