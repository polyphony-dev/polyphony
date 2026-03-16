"""Tests for NewCallCollector, NewModuleInstantiator, NewArgumentApplier."""
from polyphony.compiler.ir.ir import Ctx as OldCtx, Const, Temp, Attr, New, Move, Expr, Call
from polyphony.compiler.ir import ir as new_ir
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.transformers.instantiator import (
    NewCallCollector, new_find_called_module, NewModuleInstantiator, NewArgumentApplier,
)
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def test_new_call_collector_imports():
    """Verify NewCallCollector can be imported."""
    collector = NewCallCollector()
    assert hasattr(collector, 'calls')
    assert collector.calls == []


def test_new_call_collector_finds_calls():
    """NewCallCollector should find Call, New, and $new SysCall nodes in stms."""
    setup_test()
    top = Scope.global_scope()

    # Create a callee function
    callee = Scope.create(top, 'callee_func', {'function'}, 0)
    callee.return_type = Type.int()
    callee_blk = Block(callee, nametag='blk1')
    callee.set_entry_block(callee_blk)
    callee.set_exit_block(callee_blk)
    Block.set_order(callee_blk, 0)

    callee_sym = top.add_sym('callee_func', tags=set(), typ=Type.function(callee))

    # Create caller scope with a CALL
    caller = Scope.create(top, 'caller_func', {'function'}, 0)
    caller.add_sym('result', tags=set(), typ=Type.int())
    caller.import_sym(callee_sym)
    caller.return_type = Type.int()
    blk = Block(caller, nametag='blk1')
    caller.set_entry_block(blk)
    caller.set_exit_block(blk)
    call = Call(Temp('callee_func'), args=[], kwargs={})
    blk.append_stm(Move(Temp('result', OldCtx.STORE), call))
    Block.set_order(blk, 0)

    # Convert to new IR

    # Collect
    results = NewCallCollector().process(caller)
    assert len(results) == 1
    scope, stm, call_ir = results[0]
    assert scope is caller
    assert isinstance(call_ir, new_ir.Call)


def test_new_call_collector_finds_new():
    """NewCallCollector should find New nodes."""
    setup_test()
    top = Scope.global_scope()

    # Create a class
    klass = Scope.create(top, 'MyClass', {'class'}, 0)
    ctor = Scope.create(klass, '__init__', {'method', 'ctor'}, 0)
    ctor.add_sym('self', tags={'self'}, typ=Type.object(klass))
    ctor.return_type = Type.object(klass)
    ctor_blk = Block(ctor, nametag='blk1')
    ctor.set_entry_block(ctor_blk)
    ctor.set_exit_block(ctor_blk)
    Block.set_order(ctor_blk, 0)

    klass_sym = top.add_sym('MyClass', tags=set(), typ=Type.klass(klass))

    # Create scope with NEW
    F = Scope.create(top, 'test_func', {'function'}, 0)
    F.add_sym('obj', tags=set(), typ=Type.object(klass))
    F.import_sym(klass_sym)
    F.return_type = Type.none()
    blk = Block(F, nametag='blk1')
    F.set_entry_block(blk)
    F.set_exit_block(blk)
    new_call = New(Temp('MyClass'), args=[], kwargs={})
    blk.append_stm(Move(Temp('obj', OldCtx.STORE), new_call))
    Block.set_order(blk, 0)

    # Convert to new IR

    results = NewCallCollector().process(F)
    assert len(results) == 1
    assert isinstance(results[0][2], new_ir.New)


def test_new_module_instantiator_imports():
    """Verify NewModuleInstantiator can be imported."""
    inst = NewModuleInstantiator()
    assert hasattr(inst, 'process_modules')


def test_new_argument_applier_imports():
    """Verify NewArgumentApplier can be imported."""
    applier = NewArgumentApplier()
    assert hasattr(applier, 'process_all')
    assert hasattr(applier, 'process_scopes')
    assert hasattr(applier, '_bind_args')
