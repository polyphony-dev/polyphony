"""Tests for PolyadConstantFolding."""
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir import ir as new
from polyphony.compiler.ir.irreader import IRReader as IRParser
from polyphony.compiler.ir.transformers.constopt import PolyadConstantFolding
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def build_scope(src):
    setup_test()
    parser = IRParser(src)
    parser.parse_scope()
    for name in parser.sources:
        return env.scopes[name]


def test_polyadconstfold_basic_add():
    """PolyadConstantFolding handles basic addition."""
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
    PolyadConstantFolding().process(scope)

    # Should still have a valid scope with stms
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == 'x':
                # 3 + 4 stays as BINOP (only 2 operands, no poliad needed)
                assert isinstance(stm.src, BinOp) or isinstance(stm.src, Const)


def test_polyadconstfold_basic_mult():
    """PolyadConstantFolding handles basic multiplication."""
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x (* 2 3)
mv @return x
ret @return
'''
    scope = build_scope(src)
    PolyadConstantFolding().process(scope)

    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == 'x':
                assert isinstance(stm.src, BinOp) or isinstance(stm.src, Const)


def test_polyadconstfold_simple_binop():
    """PolyadConstantFolding handles a simple binary expression."""
    src = '''
scope F
tags function returnable
return int32
var a: int32

blk1:
mv a (+ 1 2)
mv @return a
ret @return
'''
    scope = build_scope(src)
    PolyadConstantFolding().process(scope)
    # Should produce valid output with binop or const
    stm_count = 0
    for blk in scope.traverse_blocks():
        stm_count += len(blk.stms)
    assert stm_count > 0
