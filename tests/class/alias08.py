from polyphony import testbench

class D:
    def get_v(self, v):
        return v
    
class C:
    def __init__(self, v):
        self.v = v

def alias08(x):
    s = 0
    for i in range(x):
        c = C(i)
        s += c.v
    return s

@testbench
def test():
    assert 1+2+3 == alias08(4)
    assert 0 == alias08(0)
