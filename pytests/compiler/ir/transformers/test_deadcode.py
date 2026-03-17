"""Tests for DeadCodeEliminator."""
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir import ir as new
from polyphony.compiler.ir.irreader import IRReader as IRParser
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.transformers.deadcode import DeadCodeEliminator
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def build_scope(src):
    setup_test()
    parser = IRParser(src)
    parser.parse_scope()
    for name in parser.sources:
        return env.scopes[name]


# ===========================================================
# DeadCodeEliminator
# ===========================================================

def test_dead_unused_variable():
    """DeadCodeEliminator removes an unused variable assignment."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var dead: int32

blk1:
mv dead 42
mv @return 10
ret @return
'''
    scope = build_scope(src)
    DeadCodeEliminator().process(scope)
    # 'dead' is unused, so 'mv dead 42' should be removed
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == 'dead':
                assert False, "Dead assignment to 'dead' should have been removed"


def test_used_variable_preserved():
    """DeadCodeEliminator preserves an assignment to a used variable."""
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
    DeadCodeEliminator().process(scope)
    # x is used, so 'mv x 42' should be preserved
    found_x = False
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == 'x':
                found_x = True
    assert found_x, "Assignment to used variable 'x' should be preserved"


def test_skip_namespace_scope():
    """DeadCodeEliminator skips namespace scopes."""
    src = '''
scope N
tags namespace
var x: int32

blk1:
mv x 42
'''
    scope = build_scope(src)
    DeadCodeEliminator().process(scope)
    # Should not crash, and should not remove anything (skipped)
    found_x = False
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == 'x':
                found_x = True
    assert found_x, "Namespace scope should be skipped"


def test_skip_class_scope():
    """DeadCodeEliminator skips class scopes."""
    src = '''
scope C
tags class
var x: int32

blk1:
mv x 42
'''
    scope = build_scope(src)
    DeadCodeEliminator().process(scope)
    # Should not crash, and should not remove anything (skipped)
    found_x = False
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == 'x':
                found_x = True
    assert found_x, "Class scope should be skipped"


def test_call_expression_preserved():
    """DeadCodeEliminator preserves call expressions (side effects)."""
    src = '''
scope F
tags function
var g: function(F)

blk1:
expr (call g)
'''
    scope = build_scope(src)
    DeadCodeEliminator().process(scope)
    # Call expression should be preserved
    found_expr = False
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Expr) and isinstance(stm.exp, Call):
                found_expr = True
    assert found_expr, "Call expression should be preserved"


def test_dead_expr_without_call():
    """DeadCodeEliminator removes Expr statements that are not calls."""
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 10
expr (+ 1 2)
'''
    scope = build_scope(src)
    DeadCodeEliminator().process(scope)
    # Expr with BinOp (no side effects) should be removed
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Expr) and isinstance(stm.exp, BinOp):
                assert False, "Expr with BinOp should be removed (dead code)"


def test_multiple_dead_variables():
    """DeadCodeEliminator removes multiple dead variables."""
    src = '''
scope F
tags function returnable
return int32
var a: int32
var b: int32
var c: int32

blk1:
mv a 1
mv b 2
mv c 3
mv @return 0
ret @return
'''
    scope = build_scope(src)
    DeadCodeEliminator().process(scope)
    # a, b, c are all unused, should be removed
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp):
                assert stm.dst.name not in ('a', 'b', 'c'), \
                    f"Dead variable '{stm.dst.name}' should have been removed"


def test_mstore_expr_preserved():
    """DeadCodeEliminator preserves Expr with MStore (side effects)."""
    src = '''
scope F
tags function
var mem: list<int32>[10]
var x: int32

blk1:
mv x 5
expr (mst mem 0 x)
'''
    scope = build_scope(src)
    DeadCodeEliminator().process(scope)
    # MStore has side effects, should be preserved
    found_mstore = False
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Expr) and isinstance(stm.exp, MStore):
                found_mstore = True
    assert found_mstore, "Expr with MStore should be preserved"


def test_call_result_unused_preserved():
    """DeadCodeEliminator preserves Move from Call even if result unused."""
    src = '''
scope F
tags function returnable
return int32
var g: function(F)
var x: int32

blk1:
mv x (call g)
mv @return 0
ret @return
'''
    scope = build_scope(src)
    DeadCodeEliminator().process(scope)
    # Call is IrCallable, so Move from Call should be preserved
    found_call = False
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.src, Call):
                found_call = True
    assert found_call, "Move from Call should be preserved (side effects)"


def test_move_from_param_preserved():
    """DeadCodeEliminator preserves Move where src is a parameter."""
    src = '''
scope F
tags function returnable
param a: int32
return int32
var x: int32

blk1:
mv x @in_a
mv @return 0
ret @return
'''
    scope = build_scope(src)
    DeadCodeEliminator().process(scope)
    # x = a where a is param should be preserved
    found_x = False
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == 'x':
                found_x = True
    assert found_x, "Move from param should be preserved"


def test_dead_code_multiple_blocks():
    """DeadCodeEliminator removes dead code across multiple blocks."""
    src = '''
scope F
tags function returnable
return int32
var x: int32
var dead: int32
var c: bool

blk1:
mv c True
cj c blk2 blk3

blk2:
mv dead 1
j exit

blk3:
mv dead 2
j exit

exit:
mv @return 0
ret @return
'''
    scope = build_scope(src)
    DeadCodeEliminator().process(scope)
    # 'dead' is unused, assignments should be removed
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == 'dead':
                assert False, f"Dead assignment to 'dead' in {blk.name} should be removed"


def test_syscall_expr_preserved():
    """DeadCodeEliminator preserves Expr with SysCall (side effects)."""
    src = '''
scope F
tags function
var g: function(F)
var mem: list<int32>[10]

blk1:
expr (syscall g mem)
'''
    scope = build_scope(src)
    DeadCodeEliminator().process(scope)
    # SysCall has side effects, should be preserved
    found_syscall = False
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Expr) and isinstance(stm.exp, SysCall):
                found_syscall = True
    assert found_syscall, "Expr with SysCall should be preserved"


def test_dead_move_with_attr_dst():
    """DeadCodeEliminator preserves Move with Attr destination (not Temp)."""
    src = '''
scope C
tags class
var x: int32

scope C.__init__
tags function method ctor
param $self: object(C) { self }

blk1:
mv $self.x 10
'''
    setup_test()
    parser = IRParser(src)
    parser.parse_scope()
    scope = env.scopes.get('C.__init__')
    if scope:
        DeadCodeEliminator().process(scope)
        # Attr dst should not be removed (not Temp, so break at line 38)
        found_attr = False
        for blk in scope.traverse_blocks():
            for stm in blk.stms:
                if isinstance(stm, Move) and isinstance(stm.dst, Attr):
                    found_attr = True
        assert found_attr, "Attr dst Move should be preserved"


def test_dead_var_with_path_exp():
    """DeadCodeEliminator handles blocks with path_exp set."""
    src = '''
scope F
tags function returnable
return int32
var dead: int32
var c: bool

blk1:
mv c True
cj c blk2 exit

blk2:
mv dead 42
j exit

exit:
mv @return 0
ret @return
'''
    scope = build_scope(src)
    # Set path_exp on blk2 to be a Temp (testing lines 44-46)
    for blk in scope.traverse_blocks():
        if blk.nametag == 'blk2':
            blk.path_exp = Temp(name='c')
    DeadCodeEliminator().process(scope)
    # 'dead' is unused, should still be removed
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == 'dead':
                assert False, "Dead 'dead' should still be removed despite path_exp"


def test_dead_var_same_as_path_exp():
    """DeadCodeEliminator preserves var when it's used in block path_exp."""
    src = '''
scope F
tags function returnable
return int32
var cond: int32

blk1:
mv cond 1
mv @return 0
ret @return
'''
    scope = build_scope(src)
    # Set path_exp to use 'cond' so line 49 (path_sym is var_sym) triggers
    scope.entry_block.path_exp = Temp(name='cond')
    DeadCodeEliminator().process(scope)
    # 'cond' is used in path_exp, so it should be preserved
    found_cond = False
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.dst, Temp) and stm.dst.name == 'cond':
                found_cond = True
    assert found_cond, "Variable used in path_exp should be preserved"
