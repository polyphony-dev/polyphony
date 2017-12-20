from polyphony import testbench


class C:
    def __init__(self):
        self.v1 = 0
        self.v2 = 0

    def set_v(self, i, v):
        if i == 0:
            pass
        elif i == 1:
            self.v1 = v
        elif i == 2:
            self.v2 = v
        else:
            return


def cfg01():
    c = C()
    c.set_v(1, 10)
    c.set_v(2, 20)
    return c.v1 + c.v2


@testbench
def test():
    assert 30 == cfg01()


test()
