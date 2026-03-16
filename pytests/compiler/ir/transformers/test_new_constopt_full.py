"""Tests for NewConstantOpt (full version with worklist)."""
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir import ir as new
from polyphony.compiler.ir.irreader import IRReader as IRParser
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.transformers.constopt import NewConstantOpt
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def build_scope(src):
    setup_test()
    parser = IRParser(src)
    parser.parse_scope()
    for name in parser.sources:
        return env.scopes[name]


def test_constant_propagation_basic():
    """NewConstantOpt propagates constant assignments to uses."""
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
    NewConstantOpt().process(scope)

    # After constopt, x=10 should be propagated: y=10, @return=10
    exit_blk = list(scope.traverse_blocks())[-1]
    for stm in exit_blk.stms:
        if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
            assert isinstance(stm.src, Const), f'Expected CONST but got {type(stm.src).__name__}'
            assert stm.src.value == 10


def test_constant_folding_binop():
    """NewConstantOpt folds binary operations with constant operands."""
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x (+ 3 4)
mv @return x
ret @return
'''
    scope = build_scope(src)
    NewConstantOpt().process(scope)

    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const), f'Expected CONST but got {type(stm.src).__name__}'
                assert stm.src.value == 7


def test_constant_folding_subtraction():
    """NewConstantOpt folds subtraction with constant operands."""
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x (- 10 3)
mv @return x
ret @return
'''
    scope = build_scope(src)
    NewConstantOpt().process(scope)

    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const), f'Expected CONST but got {type(stm.src).__name__}'
                assert stm.src.value == 7


def test_constant_folding_relop():
    """NewConstantOpt folds relational operations with constant operands."""
    src = '''
scope F
tags function returnable
return bool
var x: bool

blk1:
mv x (< 3 5)
mv @return x
ret @return
'''
    scope = build_scope(src)
    NewConstantOpt().process(scope)

    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const), f'Expected CONST but got {type(stm.src).__name__}'
                assert stm.src.value == True


def test_cjump_constant_true():
    """NewConstantOpt converts CJUMP with constant True to JUMP."""
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 1
cj True blk2 blk3

blk2:
mv @return 10
ret @return

blk3:
mv @return 20
ret @return
'''
    scope = build_scope(src)
    NewConstantOpt().process(scope)

    entry = scope.entry_block
    last_stm = entry.stms[-1]
    assert isinstance(last_stm, Jump), f'Expected JUMP but got {type(last_stm).__name__}'


def test_cjump_constant_false():
    """NewConstantOpt converts CJUMP with constant False to JUMP to false branch."""
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 1
cj False blk2 blk3

blk2:
mv @return 10
ret @return

blk3:
mv @return 20
ret @return
'''
    scope = build_scope(src)
    NewConstantOpt().process(scope)

    entry = scope.entry_block
    last_stm = entry.stms[-1]
    assert isinstance(last_stm, Jump), f'Expected JUMP but got {type(last_stm).__name__}'


def test_constant_folding_multiply():
    """NewConstantOpt folds multiplication with constant operands."""
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x (* 3 5)
mv @return x
ret @return
'''
    scope = build_scope(src)
    NewConstantOpt().process(scope)

    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const), f'Expected CONST but got {type(stm.src).__name__}'
                assert stm.src.value == 15


def test_class_scope_skipped():
    """NewConstantOpt skips class scopes."""
    src = '''
scope C
tags class
var x: int32

blk1:
mv x 10
'''
    scope = build_scope(src)
    # Should not crash
    NewConstantOpt().process(scope)


def test_multi_step_constant_folding():
    """NewConstantOpt folds constants across multiple assignment steps."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var y: int32
var z: int32

blk1:
mv x 3
mv y (+ x 4)
mv z (+ y x)
mv @return z
ret @return
'''
    scope = build_scope(src)
    NewConstantOpt().process(scope)

    # @return should be folded to constant 10
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == '@return':
                assert isinstance(stm.src, Const), f'Expected CONST, got {type(stm.src).__name__}'
                assert stm.src.value == 10


def test_dead_code_removal():
    """NewConstantOpt removes dead constant assignments after propagation."""
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 42
mv @return x
ret @return
'''
    scope = build_scope(src)
    NewConstantOpt().process(scope)

    # The 'mv x 42' should be removed (dead after propagation)
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == 'x':
                assert False, 'Dead assignment to x should have been removed'
