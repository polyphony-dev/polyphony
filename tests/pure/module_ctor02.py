from polyphony import pure
from polyphony import module
from polyphony import testbench
from polyphony.timing import wait_value
from polyphony.io import Port
from polyphony.typing import bit


@pure
def initialize_1(m):
    for i in range(10):
        inp = 'i' + str(i)
        outp = 'o' + str(i)
        m.__dict__[inp] = Port(bit, 'in')
        m.__dict__[outp] = Port(bit, 'out')
    initialize_2(m)


@pure
def initialize_2(m):
    for i in range(10):
        inp = 'i' + str(i)
        outp = 'o' + str(i)
        tmp = Port(bit, 'any')
        m.append_worker(m.worker, 'front' + str(i), m.__dict__[inp], tmp)
        m.append_worker(m.worker, 'back' + str(i), tmp, m.__dict__[outp])


@module
class ModuleCtor02:
    @pure
    def __init__(self):
        initialize_1(self)

    def worker(self, name, i, o):
        wait_value(1, i)
        print('worker', name, i.rd())
        o.wr(1)


@testbench
def test(m):
    m.i0.wr(1)
    m.i1.wr(1)
    m.i2.wr(1)
    m.i3.wr(1)
    m.i4.wr(1)
    m.i5.wr(1)
    m.i6.wr(1)
    m.i7.wr(1)
    m.i8.wr(1)
    m.i9.wr(1)
    wait_value(1, m.o0, m.o1, m.o2, m.o3, m.o4, m.o5, m.o6, m.o7, m.o8, m.o9)
    assert m.o0.rd() == 1
    assert m.o1.rd() == 1
    assert m.o2.rd() == 1
    assert m.o3.rd() == 1
    assert m.o4.rd() == 1
    assert m.o5.rd() == 1
    assert m.o6.rd() == 1
    assert m.o7.rd() == 1
    assert m.o8.rd() == 1
    assert m.o9.rd() == 1


m = ModuleCtor02()
test(m)
