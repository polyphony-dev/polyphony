from polyphony.compiler.ir.ir import *


def test_1():
    func1 = Expr(SysCall(Temp('func'), [], {}))
    func2 = Expr(SysCall(Temp('func'), [], {}))
    assert func1 is not func2
    assert func1 == func2
    xs = [func1, func2]
    assert xs.index(func1) == xs.index(func2)

def test_2():
    func1 = Expr(SysCall(Temp('func1'), [], {}))
    func2 = Expr(SysCall(Temp('func2'), [], {}))
    assert func1 is not func2
    assert func1 != func2
    xs = [func1, func2]
    assert xs.index(func1) == 0
    assert xs.index(func2) == 1

def test_class_match():
    ir = Move(Temp('a'), Const(1))

    match ir:
        case Move(dst=Temp(name='a', ctx=Ctx.LOAD), src=Const(value=1)):
            assert False
        case Move(dst=Temp(name='a'), src=Const(value=1)):
            assert True
        case Move(dst=Temp(name='a'), src=Const(value=0)):
            assert False
        case Move():
            assert False
        case _:
            assert False


def test_const_hash_identity():
    """CONST.__hash__ is identity-based, so equal CONSTs are not
    found in sets via 'in'. This documents the current (broken) behavior."""
    c1 = Const(42)
    c2 = Const(42)
    assert c1 == c2              # __eq__ compares by value
    assert hash(c1) != hash(c2)  # __hash__ is id-based
    s = {c1}
    assert c2 not in s           # same value, but not found in set
    # Workaround: use any(x.value == v for x in s)
    assert any(x.value == 42 for x in s)


def test_cmove_eq():
    """CMOVE.__eq__ now correctly compares CMove instances (bug fixed in new IR)."""
    m1 = CMove(Temp('c'), Temp('x', Ctx.STORE), Const(1))
    m2 = CMove(Temp('c'), Temp('x', Ctx.STORE), Const(1))
    # Now correctly equal with unified new IR
    assert m1 == m2
    assert m1.cond == m2.cond
    assert m1.dst == m2.dst
    assert m1.src == m2.src

