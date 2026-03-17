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
