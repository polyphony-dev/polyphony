"""Tests for NewInlineOpt and NewFlattenModule."""
from polyphony.compiler.ir.ir import Ctx as OldCtx, CONST, TEMP, ATTR, NEW, MOVE, EXPR, CALL, RET, JUMP
from polyphony.compiler.ir import ir as new_ir
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.transformers.inlineopt import (
    NewInlineOpt, NewFlattenModule,
)
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def test_new_inline_opt_imports():
    """Verify NewInlineOpt can be imported and has process_scopes."""
    opt = NewInlineOpt()
    assert hasattr(opt, 'process_scopes')


def test_new_flatten_module_imports():
    """Verify NewFlattenModule can be imported."""
    fm = NewFlattenModule()
    assert hasattr(fm, 'process')


def test_new_flatten_module_no_parent():
    """NewFlattenModule should return empty list for non-module scopes."""
    setup_test()
    top = Scope.global_scope()

    # Create a function scope (not in a module)
    F = Scope.create(top, 'test_func', {'function'}, 0)
    F.return_type = Type.int()
    blk = Block(F, nametag='blk1')
    F.set_entry_block(blk)
    F.set_exit_block(blk)
    blk.append_stm(MOVE(TEMP('x', OldCtx.STORE), CONST(0)))
    Block.set_order(blk, 0)

    scopes = NewFlattenModule().process(F)
    assert scopes == [] or scopes is None or len(scopes) == 0


def test_new_inline_opt_simple_inline():
    """NewInlineOpt should inline a simple function call."""
    setup_test()
    top = Scope.global_scope()

    # Create callee: def add1(x): return x + 1
    callee = Scope.create(top, 'add1', {'function', 'returnable'}, 0)
    x_param_sym = callee.add_param_sym('x', set(), typ=Type.int())
    callee.add_param(x_param_sym, None)
    # Also add 'x' as a local symbol (param copy)
    callee.add_sym('x', tags=set(), typ=Type.int())
    ret_sym = callee.add_return_sym()
    callee.return_type = Type.int()
    callee_blk = Block(callee, nametag='blk1')
    callee.set_entry_block(callee_blk)
    callee.set_exit_block(callee_blk)
    from polyphony.compiler.ir.ir import BINOP
    # param copy: x = @in_x
    callee_blk.append_stm(MOVE(TEMP('x', OldCtx.STORE), TEMP(x_param_sym.name)))
    callee_blk.append_stm(MOVE(TEMP(ret_sym.name, OldCtx.STORE), BINOP('Add', TEMP('x'), CONST(1))))
    callee_blk.append_stm(RET(TEMP(ret_sym.name)))
    Block.set_order(callee_blk, 0)
    callee_sym = top.add_sym('add1', tags=set(), typ=Type.function(callee, Type.int(), (Type.int(),)))

    # Create testbench caller
    caller = Scope.create(top, 'test', {'function', 'testbench'}, 0)
    caller.add_sym('result', tags=set(), typ=Type.int())
    caller.import_sym(callee_sym)
    caller.return_type = Type.none()
    caller_blk = Block(caller, nametag='blk1')
    caller.set_entry_block(caller_blk)
    caller.set_exit_block(caller_blk)
    call = CALL(TEMP('add1'), args=[('x', CONST(5))], kwargs={})
    caller_blk.append_stm(MOVE(TEMP('result', OldCtx.STORE), call))
    Block.set_order(caller_blk, 0)

    # Run InlineOpt
    scopes = NewInlineOpt().process_scopes([caller])

    # After inlining, the CALL should be gone from the caller
    all_stms = []
    for blk in caller.traverse_blocks():
        all_stms.extend(blk.stms)
    # Should not have any CALL to add1
    has_call = False
    for stm in all_stms:
        if isinstance(stm, MOVE) and isinstance(stm.src, CALL):
            has_call = True
    assert not has_call, 'CALL should have been inlined'
