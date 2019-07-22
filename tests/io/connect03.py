from polyphony import module, testbench
from polyphony.io import Port, flipped, connect
from polyphony.timing import timed, clkfence


@timed
class interface:
    def __init__(self):
        self.p0 = Port(int, 'in')
        self.p1 = Port(int, 'out')


@timed
def foo(p0, p1):
    x = p0.rd()
    p1.wr(x * 2)


@timed
def bar(p0, p1):
    p0.wr(10)
    clkfence()
    clkfence()
    x = p1.rd()
    print(x)
    assert x == 20


@timed
@module
class sub_module:
    def __init__(self):
        self.inf = interface()
        self.append_worker(foo, self.inf.p0, self.inf.p1, loop=True)


@timed
@module
class connect03:
    def __init__(self):
        self.sub = sub_module()
        self.inf = flipped(interface())

        connect(self.sub.inf, self.inf)
        # connect() is equivalent to
        #self.sub.inf.p0.assign(lambda:self.inf.p0.rd())
        #self.inf.p1.assign(lambda:self.sub.inf.p1.rd())

        self.append_worker(bar, self.inf.p0, self.inf.p1, loop=True)


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
