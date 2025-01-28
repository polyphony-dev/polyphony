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
class connect01:
    def __init__(self):
        self._sub = sub_module()
        self._inf = flipped(interface())

        connect(self._sub.inf, self._inf)
        # connect() is equivalent to
        # self._sub.inf.p0.assign(lambda:self._inf.p0.rd())
        # self._inf.p1.assign(lambda:self._sub.inf.p1.rd())

        self.append_worker(self.main, loop=True)

    def main(self):
        self._inf.p0.wr(10)
        clkfence()
        clkfence()
        x = self._inf.p1.rd()
        print(x)
        assert x == 20


m = connect01()


@timed
@testbench
def test(m):
    clkfence()
    clkfence()
    clkfence()
    clkfence()
    clkfence()


test(m)
