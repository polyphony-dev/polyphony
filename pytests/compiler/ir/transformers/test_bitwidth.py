"""Tests for TempVarWidthSetter."""
from polyphony.compiler.ir.ir import Ctx, Move, Ret, Temp
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.transformers.bitwidth import TempVarWidthSetter
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def _make_scope():
    setup_test()
    scope = Scope.create(None, 'BitwidthTest', {'function', 'returnable'}, 0)
    scope.return_type = Type.int()
    scope.add_return_sym(Type.int())
    return scope


def _build_and_run(scope, stms):
    """Build a block with stms, run TempVarWidthSetter, return scope for inspection."""
    blk = Block(scope, nametag='entry')
    scope.set_entry_block(blk)
    scope.set_exit_block(blk)
    for stm in stms:
        blk.append_stm(stm)
    blk.append_stm(Ret(Temp('@return')))
    setter = TempVarWidthSetter()
    setter.process(scope)
    return scope


# ============================================================
# All int temps same width (no change)
# ============================================================

def test_same_width_no_change():
    """All int temps with same width -> widths unchanged."""
    scope = _make_scope()
    scope.add_temp('@t_a').typ = Type.int(16)
    scope.add_temp('@t_b').typ = Type.int(16)

    t_a_name = [s.name for s in scope.find_syms_by_tags({'temp'}) if 'a' in s.name][0]
    t_b_name = [s.name for s in scope.find_syms_by_tags({'temp'}) if 'b' in s.name][0]

    mv = Move(dst=Temp(t_a_name, Ctx.STORE), src=Temp(t_b_name))
    _build_and_run(scope, [mv])

    sym_a = scope.find_sym(t_a_name)
    sym_b = scope.find_sym(t_b_name)
    assert sym_a.typ.width == 16
    assert sym_b.typ.width == 16


# ============================================================
# Mixed-width int temps (harmonized to max)
# ============================================================

def test_mixed_width_harmonized():
    """Temps with different widths -> all temps widened to max."""
    scope = _make_scope()
    sym_a = scope.add_temp('@t_a')
    sym_a.typ = Type.int(8)
    sym_b = scope.add_temp('@t_b')
    sym_b.typ = Type.int(32)

    mv = Move(dst=Temp(sym_a.name, Ctx.STORE), src=Temp(sym_b.name))
    _build_and_run(scope, [mv])

    assert sym_a.typ.width == 32
    assert sym_b.typ.width == 32


# ============================================================
# Non-int temps (skipped)
# ============================================================

def test_non_int_temps_skipped():
    """Non-int type temps are not tracked or modified."""
    scope = _make_scope()
    sym_a = scope.add_temp('@t_a')
    sym_a.typ = Type.bool()
    scope.add_sym('x', tags=set(), typ=Type.int(16))

    mv = Move(dst=Temp(sym_a.name, Ctx.STORE), src=Temp('x'))
    _build_and_run(scope, [mv])

    # Bool temp should not be modified
    assert sym_a.typ.is_bool()


# ============================================================
# Non-temp int symbols (tracked in int_types but not modified)
# ============================================================

def test_non_temp_int_not_modified():
    """Non-temp int symbols contribute to max_width but are not modified."""
    scope = _make_scope()
    sym_t = scope.add_temp('@t_a')
    sym_t.typ = Type.int(8)
    scope.add_sym('x', tags=set(), typ=Type.int(32))

    mv = Move(dst=Temp(sym_t.name, Ctx.STORE), src=Temp('x'))
    _build_and_run(scope, [mv])

    # Temp should be widened to 32 (max of 8 and 32)
    assert sym_t.typ.width == 32
    # Non-temp 'x' should remain at 32
    sym_x = scope.find_sym('x')
    assert sym_x.typ.width == 32


# ============================================================
# No temps at all (no changes)
# ============================================================

def test_no_temps_no_changes():
    """Move with only non-temp symbols -> no modifications."""
    scope = _make_scope()
    scope.add_sym('x', tags=set(), typ=Type.int(16))
    scope.add_sym('y', tags=set(), typ=Type.int(32))

    mv = Move(dst=Temp('x', Ctx.STORE), src=Temp('y'))
    _build_and_run(scope, [mv])

    sym_x = scope.find_sym('x')
    sym_y = scope.find_sym('y')
    assert sym_x.typ.width == 16
    assert sym_y.typ.width == 32
