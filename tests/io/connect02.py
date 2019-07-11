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
        self.append_worker(self.main, loop=True)

    def main(self):
        x = self.inf.p0.rd()
        self.inf.p1.wr(x * 2)


@timed
@module
class connect02:
    def __init__(self):
        self.sub = sub_module()
        self.inf = flipped(interface())

        connect(self.sub.inf.p0, self.inf.p0)
        connect(self.sub.inf.p1, self.inf.p1)
        # connect() is equivalent to
        #self.sub.inf.p0.assign(lambda:self.inf.p0.rd())
        #self.inf.p1.assign(lambda:self.sub.inf.p1.rd())

        self.append_worker(self.main, loop=True)

    def main(self):
        self.inf.p0.wr(10)
        clkfence()
        clkfence()
        x = self.inf.p1.rd()
        print(x)
        assert x == 20


m = connect02()


@timed
@testbench
def test(m):
    clkfence()
    clkfence()
    clkfence()
    clkfence()
    clkfence()


test(m)
