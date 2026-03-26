from polyphony.compiler import compile
from polyphony.simulator import Simulator
from polyphony.timing import clkfence, clksleep, clktime


def test(source, target, args, test_case):
    model = compile(source, target, args=tuple(args.split(',')) if args else ())
    with Simulator(model):
        test_case(model)


def test_interface(p01):
    # 0
    p01.i.write(1)
    clkfence()
    # 1
    # read from in0 at module
    clkfence()
    # 2
    # write to out0 at module
    clkfence()
    # 3
    print(p01.o.read())
    assert 1 == p01.o.read()
    p01.i.write(2)
    clkfence()
    # 4
    # read and write at module
    clkfence()
    # 5
    print(p01.o.read())
    assert 2 == p01.o.read()

test('tests/io/interface01.py', 'interface01', '', test_interface)


def test_handshake(p01):
    p01.i.wr(2)
    assert p01.o.rd() == 4

    p01.i.wr(4)
    assert p01.o.rd() == 16

    print('OK~!')

#test('tests/io/handshake.py', 'handshake_demo', '', test_handshake)
