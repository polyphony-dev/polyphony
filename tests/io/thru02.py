from polyphony import module, testbench
from polyphony.io import Port, thru
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
class thru02:
    def __init__(self):
        self.sub = sub_module()
        self.inf = interface()

        thru(self.inf.p0, self.sub.inf.p0)
        thru(self.inf.p1, self.sub.inf.p1)
        # thru() is equivalent to
        #self.sub.inf.p0.assign(lambda:self.inf.p0.rd())
        #self.inf.p1.assign(lambda:self.sub.inf.p1.rd())


m = thru02()


@timed
@testbench
def test(m):
    m.inf.p0.wr(10)
    clkfence()
    clkfence()
    x = m.inf.p1.rd()
    print(x)
    assert x == 20


test(m)
