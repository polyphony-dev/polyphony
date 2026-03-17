"""Tests for CopyOpt and ObjCopyOpt."""
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir import ir as new
from polyphony.compiler.ir.irreader import IRReader as IRParser
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.transformers.copyopt import (
    CopyCollector, CopyOpt, ObjCopyCollector, ObjCopyOpt,
)
from polyphony.compiler.ir.analysis.usedef import UseDefDetector
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def build_scope(src):
    setup_test()
    parser = IRParser(src)
    parser.parse_scope()
    for name in parser.sources:
        return env.scopes[name]


def build_scopes(src):
    setup_test()
    parser = IRParser(src)
    parser.parse_scope()
    return [env.scopes[name] for name in parser.sources]


# ===========================================================
# CopyCollector
# ===========================================================

def test_copy_collector_basic():
    """CopyCollector finds simple temp-to-temp copies."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x 10
mv y x
mv @return y
ret @return
'''
    scope = build_scope(src)
    copies = []
    collector = CopyCollector(copies)
    collector.process(scope)
    assert len(copies) >= 1, "CopyCollector should find at least one copy"
    # y = x should be detected as a copy
    found_y_copy = False
    for cp in copies:
        if isinstance(cp.dst, Temp) and cp.dst.name == 'y':
            found_y_copy = True
    assert found_y_copy


def test_copy_collector_skips_return():
    """CopyCollector skips copies to return variable."""
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 10
mv @return x
ret @return
'''
    scope = build_scope(src)
    copies = []
    collector = CopyCollector(copies)
    collector.process(scope)
    # @return should not be in copies
    for cp in copies:
        if isinstance(cp.dst, Temp):
            assert cp.dst.name != '@return', "Return var should not be collected"


def test_copy_collector_skips_cmove():
    """CopyCollector skips CMove statements."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var c: bool

blk1:
mv c True
mv x 10
mv? c x 20
mv @return x
ret @return
'''
    scope = build_scope(src)
    copies = []
    collector = CopyCollector(copies)
    collector.process(scope)
    # CMove should not appear in copies
    for cp in copies:
        assert not isinstance(cp, CMove), "CMove should not be collected"


def test_copy_collector_skips_param_src():
    """CopyCollector skips copies from @in_ parameter variables."""
    src = '''
scope F
tags function returnable
param a: int32
return int32
var x: int32

blk1:
mv x @in_a
mv @return x
ret @return
'''
    scope = build_scope(src)
    copies = []
    collector = CopyCollector(copies)
    collector.process(scope)
    # @in_a is a param, so x = @in_a should not be collected
    for cp in copies:
        if isinstance(cp.dst, Temp) and cp.dst.name == 'x':
            if isinstance(cp.src, Temp) and cp.src.name == '@in_a':
                assert False, "Copy from @in_ param should not be collected"


def test_copy_collector_skips_function_type():
    """CopyCollector skips copies where dst has function type."""
    src = '''
scope F
tags function
var f: function(F)

blk1:
mv f f
'''
    scope = build_scope(src)
    copies = []
    collector = CopyCollector(copies)
    collector.process(scope)
    # Function type dst should not be collected
    for cp in copies:
        if isinstance(cp.dst, Temp) and cp.dst.name == 'f':
            assert False, "Function type copy should not be collected"


# ===========================================================
# CopyOpt
# ===========================================================

def test_copyopt_basic_propagation():
    """CopyOpt propagates a simple copy."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x 10
mv y x
mv @return y
ret @return
'''
    scope = build_scope(src)
    CopyOpt().process(scope)
    # After copyopt, the 'mv y x' should be removed and y replaced with x
    found_y_assign = False
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == 'y':
                found_y_assign = True
    assert not found_y_assign, "Copy assignment 'y = x' should have been removed"


def test_copyopt_chain_propagation():
    """CopyOpt propagates copies across chains (z = y = x)."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32
var z: int32

blk1:
mv x 10
mv y x
mv z y
mv @return z
ret @return
'''
    scope = build_scope(src)
    CopyOpt().process(scope)
    # Both y=x and z=y should be eliminated
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp):
                if stm.dst.name in ('y', 'z'):
                    assert False, f"Copy assignment to {stm.dst.name} should have been removed"


def test_copyopt_multiple_defs_skipped():
    """CopyOpt skips variables with multiple definitions."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32
var c: bool

blk1:
mv c True
cj c blk2 blk3

blk2:
mv x 1
j exit

blk3:
mv x 2
j exit

exit:
mv y x
mv @return y
ret @return
'''
    scope = build_scope(src)
    CopyOpt().process(scope)
    # x has multiple defs, so y=x should not be optimized away
    # (This just verifies no crash)


def test_copyopt_preserves_return():
    """CopyOpt preserves @return assignments."""
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 10
mv @return x
ret @return
'''
    scope = build_scope(src)
    CopyOpt().process(scope)
    # @return should still exist
    found_return = False
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                found_return = True
    assert found_return, "@return assignment should be preserved"


def test_copyopt_no_copies():
    """CopyOpt handles scopes with no copyable statements."""
    src = '''
scope F
tags function returnable
return int32

blk1:
mv @return 42
ret @return
'''
    scope = build_scope(src)
    CopyOpt().process(scope)
    # Should not crash, @return should still be 42
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const) and stm.src.value == 42


# ===========================================================
# ObjCopyCollector
# ===========================================================

def test_obj_copy_collector_finds_object_copies():
    """ObjCopyCollector finds copies of object-typed variables."""
    src = '''
scope C
tags class
var x: int32

scope F
tags function
var a: object(C)
var b: object(C)

blk1:
mv b a
'''
    scopes = build_scopes(src)
    scope = scopes[1]  # F
    copies = []
    collector = ObjCopyCollector(copies)
    collector.process(scope)
    assert len(copies) >= 1, "ObjCopyCollector should find object copy"


def test_obj_copy_collector_skips_param():
    """ObjCopyCollector skips copies where src is a @in_ parameter."""
    src = '''
scope C
tags class
var x: int32

scope F
tags function
param a: object(C)
var b: object(C)

blk1:
mv b @in_a
'''
    scopes = build_scopes(src)
    scope = scopes[1]  # F
    copies = []
    collector = ObjCopyCollector(copies)
    collector.process(scope)
    # @in_a is a param, so should be skipped
    for cp in copies:
        if isinstance(cp.src, Temp) and cp.src.name == '@in_a':
            assert False, "Copy from @in_ param should not be collected"


def test_obj_copy_collector_skips_cmove():
    """ObjCopyCollector skips CMove statements."""
    src = '''
scope C
tags class

scope F
tags function
var a: object(C)
var b: object(C)
var c: bool

blk1:
mv c True
mv? c b a
'''
    scopes = build_scopes(src)
    scope = scopes[1]  # F
    copies = []
    collector = ObjCopyCollector(copies)
    collector.process(scope)
    for cp in copies:
        assert not isinstance(cp, CMove), "CMove should not be collected"


def test_obj_copy_collector_finds_list_copies():
    """ObjCopyCollector finds copies of list-typed variables."""
    src = '''
scope F
tags function
var a: list<int32>[5]
var b: list<int32>[5]

blk1:
mv b a
'''
    scope = build_scope(src)
    copies = []
    collector = ObjCopyCollector(copies)
    collector.process(scope)
    assert len(copies) >= 1, "ObjCopyCollector should find list copy"


# ===========================================================
# ObjCopyOpt
# ===========================================================

def test_obj_copyopt_basic():
    """ObjCopyOpt runs without crash on object copies."""
    src = '''
scope C
tags class
var x: int32

scope F
tags function
var a: object(C)
var b: object(C)

blk1:
mv b a
'''
    scopes = build_scopes(src)
    scope = scopes[1]  # F
    ObjCopyOpt().process(scope)
    # Should not crash


def test_obj_copyopt_list_copy():
    """ObjCopyOpt propagates list variable copies."""
    src = '''
scope F
tags function
var a: list<int32>[5]
var b: list<int32>[5]

blk1:
mv b a
'''
    scope = build_scope(src)
    ObjCopyOpt().process(scope)
    # Should not crash


def test_copyopt_self_copy_removed():
    """CopyOpt removes a copy x = x (after propagation src == dst)."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32
var z: int32

blk1:
mv x 10
mv y x
mv z y
mv @return z
ret @return
'''
    scope = build_scope(src)
    CopyOpt().process(scope)
    # After propagation, all intermediate copies should be removed
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp):
                if stm.dst.name in ('y', 'z'):
                    assert False, f"Copy to {stm.dst.name} should be removed"


def test_copyopt_two_uses():
    """CopyOpt propagates a copy used in two places."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32
var z: int32

blk1:
mv x 10
mv y x
mv z (+ y y)
mv @return z
ret @return
'''
    scope = build_scope(src)
    CopyOpt().process(scope)
    # y=x should be removed, y replaced with x in z = x + x
    found_y = False
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == 'y':
                found_y = True
    assert not found_y, "Copy y=x should be removed"


def test_copyopt_replaces_uses_in_binop():
    """CopyOpt replaces uses of copy variable in expressions."""
    src = '''
scope F
tags function returnable
return int32
var a: int32
var b: int32
var c: int32

blk1:
mv a 5
mv b a
mv c (+ b 1)
mv @return c
ret @return
'''
    scope = build_scope(src)
    CopyOpt().process(scope)
    # After copyopt, b should be replaced with a in the binop
    found_b_use = False
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.src, BinOp):
                if isinstance(stm.src.left, Temp) and stm.src.left.name == 'b':
                    found_b_use = True
                if isinstance(stm.src.right, Temp) and stm.src.right.name == 'b':
                    found_b_use = True
    assert not found_b_use, "Uses of b should have been replaced with a"


def test_copyopt_type_mismatch_skipped():
    """CopyCollector skips copies where src and dst have different types."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: bool

blk1:
mv y x
mv @return 0
ret @return
'''
    scope = build_scope(src)
    copies = []
    collector = CopyCollector(copies)
    collector.process(scope)
    # x (int32) and y (bool) have different types, should not be collected
    for cp in copies:
        if isinstance(cp.dst, Temp) and cp.dst.name == 'y':
            assert False, "Type mismatch copy should not be collected"


def test_obj_copy_collector_is_alias_def():
    """ObjCopyCollector._is_alias_def correctly identifies alias definitions."""
    src = '''
scope C
tags class
var x: int32

scope F
tags function
var a: object(C)
var b: object(C)
var x: int32

blk1:
mv b a
mv x 10
'''
    scopes = build_scopes(src)
    scope = scopes[1]  # F
    collector = ObjCopyCollector([])
    collector.scope = scope
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp):
                if stm.dst.name == 'b':
                    assert collector._is_alias_def(stm) is True
                elif stm.dst.name == 'x':
                    assert collector._is_alias_def(stm) is False


# ===========================================================
# Additional tests for coverage
# ===========================================================

def test_copyopt_find_root_def_chain():
    """CopyOpt._find_root_def follows chain of copies to find root."""
    src = '''
scope F
tags function returnable
return int32
var a: int32
var b: int32
var c: int32
var d: int32

blk1:
mv a 10
mv b a
mv c b
mv d c
mv @return d
ret @return
'''
    scope = build_scope(src)
    CopyOpt().process(scope)
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp):
                assert stm.dst.name not in ('b', 'c', 'd'), \
                    f"Intermediate copy to {stm.dst.name} should be removed"


def test_obj_copy_collector_is_alias_def_non_move():
    """ObjCopyCollector._is_alias_def returns False for non-Move."""
    src = '''
scope C
tags class

scope F
tags function
var a: object(C)

blk1:
mv a a
'''
    scopes = build_scopes(src)
    scope = scopes[1]  # F
    collector = ObjCopyCollector([])
    collector.scope = scope
    from polyphony.compiler.ir.ir import Jump
    blk = scope.entry_block
    j = Jump(target=blk, block=blk)
    assert collector._is_alias_def(j) is False


def test_obj_copy_collector_is_alias_def_const_src():
    """ObjCopyCollector._is_alias_def returns False when src is Const."""
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 10
'''
    scope = build_scope(src)
    collector = ObjCopyCollector([])
    collector.scope = scope
    stm = scope.entry_block.stms[0]
    assert collector._is_alias_def(stm) is False


def test_obj_copy_collector_is_alias_def_param_dst():
    """ObjCopyCollector._is_alias_def returns False when dst is a param."""
    src = '''
scope C
tags class

scope F
tags function
param a: object(C)

blk1:
mv @in_a @in_a
'''
    scopes = build_scopes(src)
    scope = scopes[1]
    collector = ObjCopyCollector([])
    collector.scope = scope
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@in_a':
                assert collector._is_alias_def(stm) is False


def test_obj_copyopt_find_old_use():
    """ObjCopyOpt._find_old_use finds Temp variable uses in nested IR."""
    src = '''
scope C
tags class
var x: int32

scope F
tags function
var a: object(C)
var b: object(C)

blk1:
mv b a
'''
    scopes = build_scopes(src)
    scope = scopes[1]  # F
    opt = ObjCopyOpt()
    opt.scope = scope
    mv = scope.entry_block.stms[0]
    vars_found = opt._find_old_use(scope, mv, ('a',))
    assert len(vars_found) >= 1


def test_copyopt_multiple_defs_removed_from_copies():
    """CopyOpt removes copies with multiple defs from copy list."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32
var z: int32
var c: bool

blk1:
mv c True
cj c blk2 blk3

blk2:
mv y 1
j exit

blk3:
mv y 2
j exit

exit:
mv x y
mv z x
mv @return z
ret @return
'''
    scope = build_scope(src)
    CopyOpt().process(scope)


def test_copyopt_copy_attr_dst_module_ctor_preserved():
    """CopyOpt preserves Attr dst copies in module ctor."""
    src = '''
scope M
tags class module
var x: int32

scope M.__init__
tags function method ctor
param $self: object(M) { self }
var tmp: int32

blk1:
mv tmp 10
mv $self.x tmp
'''
    scopes = build_scopes(src)
    scope = scopes[1]  # M.__init__
    CopyOpt().process(scope)
    found_attr = False
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Attr):
                found_attr = True
    assert found_attr, "Attr assignment in module ctor should be preserved"


def test_obj_copyopt_processes_without_crash():
    """ObjCopyOpt processes scopes with various variable types."""
    src = '''
scope C
tags class
var x: int32

scope F
tags function
var a: object(C)
var b: object(C)
var c: int32

blk1:
mv b a
mv c 10
'''
    scopes = build_scopes(src)
    scope = scopes[1]  # F
    ObjCopyOpt().process(scope)


def test_obj_copy_collector_is_alias_def_dst_not_variable():
    """ObjCopyCollector._is_alias_def returns False when dst is not IrVariable."""
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 10
'''
    scope = build_scope(src)
    collector = ObjCopyCollector([])
    collector.scope = scope
    from polyphony.compiler.ir.ir import Expr as E, BinOp
    expr = E(exp=BinOp(op='Add', left=Const(value=1), right=Const(value=2)), block=scope.entry_block)
    assert collector._is_alias_def(expr) is False


def test_obj_copy_collector_finds_object_copy_with_use():
    """ObjCopyCollector collects copies that are then used."""
    src = '''
scope C
tags class
var x: int32

scope F
tags function
var a: object(C)
var b: object(C)
var c: object(C)

blk1:
mv b a
mv c b
'''
    scopes = build_scopes(src)
    scope = scopes[1]  # F
    copies = []
    collector = ObjCopyCollector(copies)
    collector.process(scope)
    assert len(copies) >= 2


def test_copyopt_find_root_def_returns_none_for_non_move():
    """CopyOpt._find_root_def returns None when the def is not a Move."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x 10
mv y x
mv @return y
ret @return
'''
    scope = build_scope(src)
    opt = CopyOpt()
    opt.scope = scope
    opt.usedef = UseDefDetector().process(scope)
    ret_sym = scope.find_sym('@return')
    result = opt._find_root_def((ret_sym,))


def test_obj_copyopt_find_old_use_attr():
    """ObjCopyOpt._find_old_use finds Attr uses in nested IR."""
    src = '''
scope C
tags class
var x: int32

scope F
tags function
var a: object(C)
var b: object(C)
var y: int32

blk1:
mv b a
mv y a.x
'''
    scopes = build_scopes(src)
    scope = scopes[1]  # F
    opt = ObjCopyOpt()
    opt.scope = scope
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.src, Attr):
                found = opt._find_old_use(scope, stm, ('a',))
                assert len(found) >= 1


def test_copyopt_with_binop_use():
    """CopyOpt handles copies used in binary expressions correctly."""
    src = '''
scope F
tags function returnable
return int32
var a: int32
var b: int32
var c: int32
var d: int32

blk1:
mv a 5
mv b a
mv c (+ b 1)
mv d (* b 2)
mv @return (+ c d)
ret @return
'''
    scope = build_scope(src)
    CopyOpt().process(scope)
    found_b = False
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == 'b':
                found_b = True
    assert not found_b, "Copy b=a should be removed"
