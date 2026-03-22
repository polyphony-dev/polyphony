from unittest.mock import MagicMock
from polyphony.compiler.ir.ir import Temp, Move, Ctx
from polyphony.compiler.ir.analysis.usedef import UseDefItem


def _make_sym():
    """Return a fake Symbol (identity-based, no custom __hash__/__eq__)."""
    return MagicMock()


def test_usedefitem_eq_same_objects():
    """UseDefItems built from the same object references are equal."""
    sym = _make_sym()
    qsym = (sym,)
    var = Temp(name='x', ctx=Ctx.STORE)
    stm = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=Temp(name='y', ctx=Ctx.LOAD))
    item1 = UseDefItem(sym, qsym, var, stm, 'b0')
    item2 = UseDefItem(sym, qsym, var, stm, 'b0')
    assert item1 == item2
    assert hash(item1) == hash(item2)
    assert item1 in {item2}


def test_usedefitem_eq_diff_var_object():
    """UseDefItems with different var objects are not equal, even if var values match.
    UseDefTable tracks var by identity: the same IrVariable object must be used
    for consistent add/remove operations."""
    sym = _make_sym()
    qsym = (sym,)
    var1 = Temp(name='x', ctx=Ctx.STORE)
    var2 = Temp(name='x', ctx=Ctx.STORE)  # same value, different object
    assert var1 is not var2
    stm = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=Temp(name='y', ctx=Ctx.LOAD))
    item1 = UseDefItem(sym, qsym, var1, stm, 'b0')
    item2 = UseDefItem(sym, qsym, var2, stm, 'b0')
    assert item1 != item2  # identity-based: different objects -> not equal


def test_usedefitem_eq_diff_stm_object():
    """UseDefItems with different stm objects are not equal.
    IrStm.__hash__ = id(self), so UseDefTable keys stm by identity."""
    sym = _make_sym()
    qsym = (sym,)
    var = Temp(name='x', ctx=Ctx.STORE)
    stm1 = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=Temp(name='y', ctx=Ctx.LOAD))
    stm2 = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=Temp(name='y', ctx=Ctx.LOAD))
    assert stm1 is not stm2
    item1 = UseDefItem(sym, qsym, var, stm1, 'b0')
    item2 = UseDefItem(sym, qsym, var, stm2, 'b0')
    assert item1 != item2


def test_usedefitem_eq_diff_blk():
    """UseDefItems with different block bids are not equal."""
    sym = _make_sym()
    qsym = (sym,)
    var = Temp(name='x', ctx=Ctx.STORE)
    stm = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=Temp(name='y', ctx=Ctx.LOAD))
    item1 = UseDefItem(sym, qsym, var, stm, 'b0')
    item2 = UseDefItem(sym, qsym, var, stm, 'b1')
    assert item1 != item2
