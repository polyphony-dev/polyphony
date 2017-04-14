from polyphony import pure
from polyphony import testbench
from polyphony import module
from polyphony.timing import clksleep
from polyphony.typing import int8, int16


class Sub:
    def __init__(self, x):
        self.x:int16 = x


def w0(p0, p1):
    print('w0', p0, p1)


@module
class ModuleCtor01:
    @pure
    def __init__(self, p, q=100):
        from collections import namedtuple
        Worker = namedtuple('Worker', ('func', 'args'))

        r = 0x6666  # type: int16
        self.sub = Sub(1000)

        workers = [
            Worker(func=self.w1, args=(p, 'a')),
            Worker(func=w0, args=(p * q, 'b')),
            Worker(func=w0, args=(p * r, 'c')),
            Worker(func=w0, args=(self.sub.x, 'd')),
        ]
        for fn, args in workers:
            self.append_worker(fn, *args)
        self.x:int8 = 0

    def w1(self, p0, p1):
        print('w1', p0, p1)
        #self.x = 111


m = ModuleCtor01(1)


@testbench
def test(m):
    clksleep(100)


test(m)
