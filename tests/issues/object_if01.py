from polyphony import module, testbench, is_worker_running
from polyphony.io import Port


class Interface:
    def __init__(self):
        self.i0 = Port(int, 'in')
        self.i1 = Port(int, 'in')


class Object:
    def __init__(self):
        self.inf0 = Interface()
        self.inf1 = Interface()

    def read(self):
        return self.inf0.i0.rd() * self.inf0.i1.rd() + self.inf1.i0.rd() * self.inf1.i1.rd()


@module
class object_if01:
    def __init__(self):
        self.mode = Port(int, 'in')
        self.result = Port(int, 'out')
        self.a = Object()
        self.b = Object()
        self.c = Object()
        self.append_worker(self.main)

    def read(self, obj0, obj1):
        x = obj0.read()
        y = obj1.read()
        return x - y

    def main(self):
        while is_worker_running():
            mode = self.mode.rd()
            ret = 0
            if mode == 0:
                ret = self.read(self.a, self.b)
            elif mode == 1:
                ret = self.read(self.b, self.c)
            elif mode == 2:
                pass
            else:
                ret = self.read(self.c, self.a)
            self.result.wr(ret)


m = object_if01()


@testbench
def test(m):
    m.a.inf0.i0.wr(10)
    m.a.inf0.i1.wr(20)
    m.a.inf1.i0.wr(30)
    m.a.inf1.i1.wr(40)
    m.b.inf0.i0.wr(50)
    m.b.inf0.i1.wr(60)
    m.b.inf1.i0.wr(70)
    m.b.inf1.i1.wr(80)
    m.c.inf0.i0.wr(90)
    m.c.inf0.i1.wr(100)
    m.c.inf1.i0.wr(110)
    m.c.inf1.i1.wr(120)
    m.mode.wr(0)
    print(m.result.rd())

    m.mode.wr(1)
    print(m.result.rd())

    m.mode.wr(2)
    print(m.result.rd())

    m.mode.wr(3)
    print(m.result.rd())


test(m)