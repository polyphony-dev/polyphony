from unittest.mock import MagicMock
from polyphony.compiler.ir.ir import Temp, Move, Ctx
from polyphony.compiler.ir.analysis.usedef import UseDefItem


def _make_sym():
    """Return a fake Symbol (identity-based, no custom __hash__/__eq__).

    MagicMock's default hash is identity-based (id(obj)), matching
    the real Symbol behavior. Used with id(sym) in UseDefItem.__hash__.
    """
    return MagicMock()


def test_usedefitem_eq_same_var_value():
    """Two UseDefItems with different var objects but same value should be equal."""
    sym = _make_sym()
    qsym = (sym,)
    var1 = Temp(name='x', ctx=Ctx.STORE)
    var2 = Temp(name='x', ctx=Ctx.STORE)  # different object, same value
    assert var1 is not var2
    stm = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=Temp(name='y', ctx=Ctx.LOAD))
    item1 = UseDefItem(sym, qsym, var1, stm, 'b0')
    item2 = UseDefItem(sym, qsym, var2, stm, 'b0')
    assert item1 == item2
    assert hash(item1) == hash(item2)
    assert item1 in {item2}


def test_usedefitem_eq_diff_var():
    """UseDefItems with different var names should not be equal."""
    sym = _make_sym()
    qsym = (sym,)
    var1 = Temp(name='x', ctx=Ctx.STORE)
    var2 = Temp(name='y', ctx=Ctx.STORE)
    stm = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=Temp(name='z', ctx=Ctx.LOAD))
    item1 = UseDefItem(sym, qsym, var1, stm, 'b0')
    item2 = UseDefItem(sym, qsym, var2, stm, 'b0')
    assert item1 != item2


def test_usedefitem_eq_diff_stm():
    """UseDefItems with different stm objects should not be equal (stm is identity-based).

    Note: IrStm.__hash__ = id(self) but IrStm.__eq__ is value-based.
    UseDefItem intentionally uses 'is' for stm to respect the id-based hash contract.
    """
    sym = _make_sym()
    qsym = (sym,)
    var = Temp(name='x', ctx=Ctx.STORE)
    stm1 = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=Temp(name='y', ctx=Ctx.LOAD))
    stm2 = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=Temp(name='y', ctx=Ctx.LOAD))
    assert stm1 is not stm2
    item1 = UseDefItem(sym, qsym, var, stm1, 'b0')
    item2 = UseDefItem(sym, qsym, var, stm2, 'b0')
    assert item1 != item2
    assert hash(item1) != hash(item2)  # id(stm1) != id(stm2)


def test_usedefitem_eq_diff_blk():
    """UseDefItems with different block bids should not be equal."""
    sym = _make_sym()
    qsym = (sym,)
    var = Temp(name='x', ctx=Ctx.STORE)
    stm = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=Temp(name='y', ctx=Ctx.LOAD))
    item1 = UseDefItem(sym, qsym, var, stm, 'b0')
    item2 = UseDefItem(sym, qsym, var, stm, 'b1')
    assert item1 != item2


def test_usedefitem_attr_value_based():
    """Attr vars with same name/exp/attr should be considered equal (value-based)."""
    from polyphony.compiler.ir.ir import Attr
    sym = _make_sym()
    qsym = (sym,)
    exp = Temp(name='self', ctx=Ctx.LOAD)
    attr1 = Attr(exp=exp, attr='x', ctx=Ctx.STORE)
    attr2 = Attr(exp=exp, attr='x', ctx=Ctx.STORE)  # different object, same value
    assert attr1 is not attr2
    assert attr1 == attr2
    stm = Move(dst=attr1, src=Temp(name='y', ctx=Ctx.LOAD))
    item1 = UseDefItem(sym, qsym, attr1, stm, 'b0')
    item2 = UseDefItem(sym, qsym, attr2, stm, 'b0')
    assert item1 == item2
    assert hash(item1) == hash(item2)
