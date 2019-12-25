from polyphony import module, testbench
from polyphony.io import Port, flipped, connect
from polyphony.timing import timed, clkfence


@timed
class interface:
    def __init__(self):
        self.p0 = Port(int, 'in')
        self.p1 = Port(int, 'out')


@timed
@module
class sub_module:
    def __init__(self):
        self.inf = interface()
        self.append_worker(foo, self.inf.p0, self.inf.p1, loop=True)


@timed
def foo(p0, p1):
    x = p0.rd()
    p1.wr(x * 2)


@timed
@module
class connect03:
    def __init__(self):
        self._sub = sub_module()
        self._inf = flipped(interface())

        connect(self._sub.inf, self._inf)

        self.append_worker(bar, self._inf.p0, self._inf.p1, loop=True)


@timed
def bar(p0, p1):
    p0.wr(10)
    clkfence()
    clkfence()
    x = p1.rd()
    print(x)
    assert x == 20


m = connect03()


@timed
@testbench
def test(m):
    clkfence()
    clkfence()
    clkfence()
    clkfence()
    clkfence()


test(m)
