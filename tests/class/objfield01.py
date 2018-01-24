from polyphony import testbench


class C:
    def __init__(self, x, y):
        o1 = SubObj(x)
        o2 = SubObj(y)
        self.o = Obj(o1, o2)

    def func(self, v1, v2):
        self.o.add(v1, v2)

    def result(self):
        return self.o.result()


class Obj:
    def __init__(self, o1, o2):
        self.o1 = o1
        self.o2 = o2

    def add(self, v1, v2):
        self.o1.add(v1)
        self.o2.add(v2)

    def result(self):
        return self.o1.x + self.o2.x


class SubObj:
    def __init__(self, x):
        self.x = x

    def add(self, i):
        self.x += i


def objfield01(x, y):
    c = C(x, y)
    c.func(1, 2)
    return c.result()


@testbench
def test():
    assert 33 == objfield01(10, 20)


test()
