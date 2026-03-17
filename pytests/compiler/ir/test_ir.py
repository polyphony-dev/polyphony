from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir.ir import (
    name2var, move_ir, conds2str,
)
from pytests.compiler.base import make_block


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


# ============================================================
# __str__ methods
# ============================================================

def test_unop_str():
    u = UnOp('USub', Const(1))
    assert str(u) == '-1'


def test_relop_str():
    r = RelOp('Eq', Temp('a'), Const(0))
    assert str(r) == '(a == 0)'


def test_condop_str():
    c = CondOp(Temp('c'), Const(1), Const(0))
    assert str(c) == '(c ? 1 : 0)'


def test_polyop_str():
    p = PolyOp('Add', [Const(1), Const(2), Const(3)])
    assert str(p) == '(+ [1, 2, 3])'


def test_call_str():
    c = Call(Temp('foo'), [('', Const(1)), ('', Temp('x'))], {})
    assert 'foo(' in str(c)


def test_call_str_with_kwargs():
    c = Call(Temp('foo'), [('', Const(1))], {'key': Const(2)})
    s = str(c)
    assert 'key=2' in s


def test_syscall_str():
    sc = SysCall(Temp('print'), [('', Const(42))], {})
    assert '!print(' in str(sc)


def test_syscall_str_with_kwargs():
    sc = SysCall(Temp('sys'), [('', Const(1))], {'end': Const(0)})
    s = str(sc)
    assert 'end=0' in s


def test_new_str():
    n = New(Temp('MyClass'), [('', Const(1))], {})
    assert '$MyClass(' in str(n)


def test_new_str_with_kwargs():
    n = New(Temp('Cls'), [('', Const(1))], {'a': Const(2)})
    s = str(n)
    assert 'a=2' in s


def test_mref_str():
    m = MRef(Temp('arr'), Const(0))
    assert str(m) == 'arr[0]'


def test_mstore_str():
    m = MStore(Temp('arr'), Const(0), Const(42))
    assert str(m) == 'mstore(arr[0], 42)'


def test_cexpr_str():
    ce = CExpr(Temp('c'), SysCall(Temp('f'), [], {}))
    assert 'c ? ' in str(ce)


def test_cmove_str():
    cm = CMove(Temp('c'), Temp('x'), Const(1))
    assert str(cm) == 'c ? x = 1'


def test_jump_str():
    blk = make_block()
    j = Jump(blk)
    assert 'jump' in str(j)


def test_cjump_str():
    blk_t = make_block()
    blk_f = make_block()
    cj = CJump(Temp('cond'), blk_t, blk_f)
    assert 'cjump' in str(cj)


def test_mcjump_str():
    blk1 = make_block()
    blk2 = make_block()
    mj = MCJump([Const(1), Const(0)], [blk1, blk2])
    s = str(mj)
    assert 'mcjump' in s


def test_phi_str():
    p = Phi(Temp('x'))
    p.args.extend([Const(1), Const(2)])
    assert 'phi(' in str(p)


def test_phi_str_with_ps():
    p = Phi(Temp('x'))
    blk1 = make_block()
    blk2 = make_block()
    p.args.extend([Const(1), Const(2)])
    p.ps.extend([blk1, blk2])
    s = str(p)
    assert 'phi(' in s
    assert '?' in s


def test_uphi_str():
    u = UPhi(Temp('x'))
    u.args.append(Const(1))
    assert 'uphi(' in str(u)


def test_lphi_str():
    lp = LPhi(Temp('x'))
    lp.args.append(Const(1))
    assert 'lphi(' in str(lp)


def test_mstm_str():
    m = MStm(stms=[Move(Temp('a'), Const(1)), Move(Temp('b'), Const(2))])
    assert 'mstm{' in str(m)


def test_ret_str():
    r = Ret(Const(0))
    assert str(r) == 'return 0'


# ============================================================
# __eq__ methods
# ============================================================

def test_unop_eq():
    u1 = UnOp('Not', Temp('a'))
    u2 = UnOp('Not', Temp('a'))
    u3 = UnOp('USub', Temp('a'))
    assert u1 == u2
    assert u1 != u3
    assert u1 != Const(1)


def test_relop_eq():
    r1 = RelOp('Lt', Temp('a'), Const(0))
    r2 = RelOp('Lt', Temp('a'), Const(0))
    r3 = RelOp('Gt', Temp('a'), Const(0))
    assert r1 == r2
    assert r1 != r3
    assert r1 != Const(0)


def test_condop_eq():
    c1 = CondOp(Temp('c'), Const(1), Const(0))
    c2 = CondOp(Temp('c'), Const(1), Const(0))
    c3 = CondOp(Temp('c'), Const(2), Const(0))
    assert c1 == c2
    assert c1 != c3
    assert c1 != Const(0)


def test_mref_eq():
    m1 = MRef(Temp('a'), Const(0))
    m2 = MRef(Temp('a'), Const(0))
    m3 = MRef(Temp('b'), Const(0))
    assert m1 == m2
    assert m1 != m3
    assert m1 != Const(0)


def test_mstore_eq():
    m1 = MStore(Temp('a'), Const(0), Const(1))
    m2 = MStore(Temp('a'), Const(0), Const(1))
    m3 = MStore(Temp('a'), Const(0), Const(2))
    assert m1 == m2
    assert m1 != m3
    assert m1 != Const(0)


def test_array_eq():
    a1 = Array([Const(1), Const(2)])
    a2 = Array([Const(1), Const(2)])
    a3 = Array([Const(1), Const(3)])
    assert a1 == a2
    assert a1 != a3
    assert a1 != Const(0)


def test_cexpr_eq():
    ce1 = CExpr(Temp('c'), SysCall(Temp('f'), [], {}))
    ce2 = CExpr(Temp('c'), SysCall(Temp('f'), [], {}))
    ce3 = CExpr(Temp('d'), SysCall(Temp('f'), [], {}))
    assert ce1 == ce2
    assert ce1 != ce3
    assert ce1 != Const(0)


def test_jump_eq():
    blk1 = make_block()
    blk2 = make_block()
    j1 = Jump(blk1)
    j2 = Jump(blk1)
    j3 = Jump(blk2)
    assert j1 == j2
    assert j1 != j3
    assert j1 != Const(0)


def test_cjump_eq():
    blk_t = make_block()
    blk_f = make_block()
    cj1 = CJump(Temp('c'), blk_t, blk_f)
    cj2 = CJump(Temp('c'), blk_t, blk_f)
    cj3 = CJump(Temp('d'), blk_t, blk_f)
    assert cj1 == cj2
    assert cj1 != cj3
    assert cj1 != Const(0)


def test_mcjump_eq():
    blk1 = make_block()
    blk2 = make_block()
    m1 = MCJump([Const(1)], [blk1])
    m2 = MCJump([Const(1)], [blk1])
    m3 = MCJump([Const(0)], [blk2])
    assert m1 == m2
    assert m1 != m3
    assert m1 != Const(0)


def test_ret_eq():
    r1 = Ret(Const(0))
    r2 = Ret(Const(0))
    r3 = Ret(Const(1))
    assert r1 == r2
    assert r1 != r3
    assert r1 != Const(0)


def test_phi_eq():
    p1 = Phi(Temp('x'))
    p2 = Phi(Temp('x'))
    p3 = Phi(Temp('y'))
    assert p1 == p2
    assert p1 != p3
    assert p1 != Const(0)


def test_mstm_eq():
    m1 = MStm(stms=[Move(Temp('a'), Const(1))])
    m2 = MStm(stms=[Move(Temp('a'), Const(1))])
    m3 = MStm(stms=[Move(Temp('b'), Const(1))])
    assert m1 == m2
    assert m1 != m3
    assert m1 != Const(0)


# ============================================================
# kids() methods
# ============================================================

def test_unop_kids():
    u = UnOp('Not', Temp('a'))
    assert len(u.kids()) == 1


def test_condop_kids():
    c = CondOp(Temp('c'), Temp('a'), Temp('b'))
    assert len(c.kids()) == 3


def test_polyop_kids():
    p = PolyOp('Add', [Const(1), Const(2)])
    assert len(p.kids()) == 2


def test_mref_kids():
    m = MRef(Temp('arr'), Const(0))
    assert len(m.kids()) == 2


def test_mstore_kids():
    m = MStore(Temp('arr'), Const(0), Const(1))
    assert len(m.kids()) == 3


def test_cexpr_kids():
    ce = CExpr(Temp('c'), SysCall(Temp('f'), [], {}))
    kids = ce.kids()
    assert len(kids) >= 2


def test_cmove_kids():
    cm = CMove(Temp('c'), Temp('x'), Const(1))
    kids = cm.kids()
    assert len(kids) == 3


def test_ret_kids():
    r = Ret(Const(0))
    assert len(r.kids()) == 1


def test_phi_kids():
    p = Phi(Temp('x'))
    p.args.extend([Const(1), None, Const(2)])
    kids = p.kids()
    # var(1) + arg1(1) + arg3(1), None is skipped
    assert len(kids) == 3


def test_array_kids():
    a = Array([Const(1), Const(2)])
    assert len(a.kids()) == 2


def test_callable_kids():
    c = Call(Temp('f'), [('', Const(1)), ('', Temp('x'))], {})
    kids = c.kids()
    assert len(kids) == 3  # func + 2 args


# ============================================================
# clone() — dict and tuple branches
# ============================================================

def test_clone_basic():
    m = Move(Temp('a'), Const(1))
    m2 = m.clone()
    assert m == m2
    assert m is not m2


def test_clone_with_override():
    m = Move(Temp('a'), Const(1))
    m2 = m.clone(src=Const(2))
    assert m2.src == Const(2)


def test_clone_with_list():
    p = Phi(Temp('x'))
    p.args.extend([Const(1), Const(2)])
    p2 = p.clone()
    assert p2.var == p.var
    assert len(p2.args) == 2


# ============================================================
# Ir.replace()
# ============================================================

def test_replace_in_move():
    old_src = Const(1)
    m = Move(Temp('a'), old_src)
    new_src = Const(2)
    result = m.replace(old_src, new_src)
    assert result is True
    assert m.src is new_src


# ============================================================
# find_vars / find_irs
# ============================================================

def test_find_vars():
    t = Temp('x')
    m = Move(t, Const(1))
    found = m.find_vars(('x',))
    # dst is x(STORE), we search for ('x',)
    assert len(found) >= 1


def test_find_irs():
    m = Move(Temp('a'), BinOp('Add', Const(1), Const(2)))
    found = m.find_irs(Const)
    assert len(found) == 2


# ============================================================
# Attr
# ============================================================

def test_attr_head_name_nested():
    inner = Temp('obj')
    mid = Attr(inner, 'field1')
    outer = Attr(mid, 'field2')
    assert outer.head_name() == 'obj'


def test_attr_tail_name():
    a = Attr(Temp('obj'), 'field')
    assert a.tail_name() == 'obj'


def test_attr_head_name_non_temp():
    """head_name returns '' when exp is neither Attr nor Temp."""
    c = Call(Temp('f'), [], {})
    a = Attr(exp=c, attr='method', name='method')
    assert a.head_name() == ''


# ============================================================
# Array
# ============================================================

def test_array_getlen():
    a = Array([Const(1), Const(2)])
    assert a.getlen() == 2


def test_array_getlen_with_repeat():
    a = Array([Const(0)], mutable=True)
    a2 = a.clone(repeat=Const(4))
    assert a2.getlen() == 4


def test_array_getlen_non_const_repeat():
    a = Array([Const(0)])
    a2 = a.clone(repeat=Temp('n'))
    assert a2.getlen() == -1


def test_array_str_long():
    items = [Const(i) for i in range(10)]
    a = Array(items)
    s = str(a)
    assert '...' in s


def test_array_str_with_repeat():
    a = Array([Const(0)])
    a2 = a.clone(repeat=Const(4))
    assert '* 4' in str(a2)


def test_array_immutable_str():
    a = Array([Const(1), Const(2)], mutable=False)
    s = str(a)
    assert s.startswith('(')
    assert s.endswith(')')


# ============================================================
# Const format
# ============================================================

def test_const_hex():
    c = Const(255, 'hex')
    assert str(c) == '0xff'


def test_const_bin():
    c = Const(5, 'bin')
    assert str(c) == '0b101'


# ============================================================
# IrStm helpers
# ============================================================

def test_is_mem_read():
    m = Move(Temp('a'), MRef(Temp('arr'), Const(0)))
    assert m.is_mem_read()
    m2 = Move(Temp('a'), Const(1))
    assert not m2.is_mem_read()


def test_is_mem_write():
    e = Expr(MStore(Temp('arr'), Const(0), Const(1)))
    assert e.is_mem_write()
    e2 = Expr(SysCall(Temp('f'), [], {}))
    assert not e2.is_mem_write()


# ============================================================
# Utility functions
# ============================================================

def test_name2var_simple():
    v = name2var('x')
    assert isinstance(v, Temp)
    assert v.name == 'x'
    assert v.ctx == Ctx.LOAD


def test_name2var_dotted():
    v = name2var('a.b.c', ctx=Ctx.STORE)
    assert isinstance(v, Attr)
    assert v.name == 'c'
    assert v.ctx == Ctx.STORE


def test_move_ir_strings():
    m = move_ir('x', 'y')
    assert isinstance(m, Move)


def test_move_ir_int_src():
    m = move_ir(42, 'y')
    assert isinstance(m.src, Const)
    assert m.src.value == 42


def test_conds2str_empty():
    assert conds2str([]) == 'None'
    assert conds2str(None) == 'None'


def test_conds2str_with_items():
    s = conds2str([(Temp('a'), True), (Temp('b'), False)])
    assert 'a == True' in s
    assert 'and' in s


# ============================================================
# Phi.remove_arg / Phi.reorder_args
# ============================================================

def test_phi_remove_arg():
    p = Phi(Temp('x'))
    a1 = Const(1)
    a2 = Const(2)
    blk1 = make_block()
    blk2 = make_block()
    p.args.extend([a1, a2])
    p.ps.extend([blk1, blk2])
    p.remove_arg(a1)
    assert len(p.args) == 1
    assert p.args[0] is a2
    assert len(p.ps) == 1


def test_phi_reorder_args():
    p = Phi(Temp('x'))
    a1 = Const(1)
    a2 = Const(2)
    a3 = Const(3)
    blk1 = make_block()
    blk2 = make_block()
    blk3 = make_block()
    p.args.extend([a1, a2, a3])
    p.ps.extend([blk1, blk2, blk3])
    p.reorder_args([2, 0, 1])
    assert p.args[0] is a3
    assert p.args[1] is a1
    assert p.args[2] is a2


# ============================================================
# IrCallable
# ============================================================

def test_callable_eq():
    c1 = Call(Temp('f'), [('', Const(1))], {})
    c2 = Call(Temp('f'), [('', Const(1))], {})
    c3 = Call(Temp('g'), [('', Const(1))], {})
    assert c1 == c2
    assert c1 != c3
    assert c1 != Const(0)


def test_callable_qualified_name():
    c = Call(Temp('f'), [], {})
    assert c.qualified_name == ('f',)
