from polyphony import module, testbench
from polyphony.io import Port, flipped, connect, thru
from polyphony.timing import timed, clkfence


@timed
class interface:
    def __init__(self):
        self.p0 = Port(int, 'in')
        self.p1 = Port(int, 'out')


@timed
@module
class sub_sub_module:
    def __init__(self):
        self.inf = interface()
        self.append_worker(self.main, loop=True)

    def main(self):
        x = self.inf.p0.rd()
        self.inf.p1.wr(x * 2)


@timed
@module
class sub_module:
    def __init__(self):
        self.public_inf = interface()
        self._sub_sub = sub_sub_module()
        thru(self.public_inf, self._sub_sub.inf)


@timed
@module
class connect04:
    def __init__(self):
        self._sub = sub_module()
        self._inf = flipped(interface())

        connect(self._sub.public_inf, self._inf)

        self.append_worker(self.main, loop=True)

    def main(self):
        self._inf.p0.wr(10)
        clkfence()
        clkfence()
        x = self._inf.p1.rd()
        print(x)
        assert x == 20


m = connect04()


@timed
@testbench
def test(m):
    clkfence()
    clkfence()
    clkfence()
    clkfence()
    clkfence()


test(m)
