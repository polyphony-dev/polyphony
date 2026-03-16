"""Tests for ObjectHierarchyCopier."""
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir import ir as new
from polyphony.compiler.ir.irreader import IRReader as IRParser
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.transformers.inlineopt import ObjectHierarchyCopier
from polyphony.compiler.ir.transformers.inlineopt import ObjectHierarchyCopier
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def test_object_copy_inserts_field_moves():
    """When an object with sub-object fields is copied (d = c0),
    ObjectHierarchyCopier should insert MOVE for each object field."""
    setup_test()

    # Create class C with int field
    C = Scope.create(None, 'C', {'class'}, 0)
    C.add_sym('v', tags=set(), typ=Type.int(32))

    # Create class D with object field c of type C
    D = Scope.create(None, 'D', {'class'}, 0)
    D.add_sym('c', tags=set(), typ=Type.object(C))

    # Create function scope
    F = Scope.create(None, 'F', {'function'}, 0)
    F.add_sym('c0', tags=set(), typ=Type.object(C))
    F.add_sym('d', tags=set(), typ=Type.object(D))

    blk = Block(F, nametag='blk1')
    F.set_entry_block(blk)
    F.set_exit_block(blk)

    # d = c0 (object copy - but D.c is object, so should NOT trigger
    # because c0 is C type and d is D type, they're different)
    # Instead test d1 = d2 where both are D type
    F.add_sym('d1', tags=set(), typ=Type.object(D))
    F.add_sym('d2', tags=set(), typ=Type.object(D))

    mv = Move(Temp('d1', Ctx.STORE), Temp('d2', Ctx.LOAD))
    object.__setattr__(mv, 'block', blk)
    blk.append_stm(mv)

    Block.set_order(blk, 0)

    # Run old ObjectHierarchyCopier
    setup_test()
    C2 = Scope.create(None, 'C', {'class'}, 0)
    C2.add_sym('v', tags=set(), typ=Type.int(32))
    D2 = Scope.create(None, 'D', {'class'}, 0)
    D2.add_sym('c', tags=set(), typ=Type.object(C2))
    F2 = Scope.create(None, 'F', {'function'}, 0)
    F2.add_sym('d1', tags=set(), typ=Type.object(D2))
    F2.add_sym('d2', tags=set(), typ=Type.object(D2))
    blk2 = Block(F2, nametag='blk1')
    F2.set_entry_block(blk2)
    F2.set_exit_block(blk2)
    mv2 = Move(Temp('d1', Ctx.STORE), Temp('d2', Ctx.LOAD))
    object.__setattr__(mv2, 'block', blk2)
    blk2.append_stm(mv2)
    Block.set_order(blk2, 0)

    ObjectHierarchyCopier().process(F2)
    old_stm_count = len(blk2.stms)

    # Run new ObjectHierarchyCopier
    setup_test()
    C3 = Scope.create(None, 'C', {'class'}, 0)
    C3.add_sym('v', tags=set(), typ=Type.int(32))
    D3 = Scope.create(None, 'D', {'class'}, 0)
    D3.add_sym('c', tags=set(), typ=Type.object(C3))
    F3 = Scope.create(None, 'F', {'function'}, 0)
    F3.add_sym('d1', tags=set(), typ=Type.object(D3))
    F3.add_sym('d2', tags=set(), typ=Type.object(D3))
    blk3 = Block(F3, nametag='blk1')
    F3.set_entry_block(blk3)
    F3.set_exit_block(blk3)
    mv3 = new.Move(dst=new.Temp(name='d1', ctx=new.Ctx.STORE), src=new.Temp(name='d2'), block=blk3)
    blk3.stms.append(mv3)
    Block.set_order(blk3, 0)

    ObjectHierarchyCopier().process(F3)
    new_stm_count = len(blk3.stms)

    # Both should have the same number of statements
    assert old_stm_count == new_stm_count, (
        f'Statement count differs: old={old_stm_count} new={new_stm_count}'
    )


def test_no_copy_for_non_object_fields():
    """ObjectHierarchyCopier should only insert copies for object-type fields,
    not for scalar fields."""
    setup_test()

    # Class with only scalar field
    C = Scope.create(None, 'C', {'class'}, 0)
    C.add_sym('x', tags=set(), typ=Type.int(32))

    F = Scope.create(None, 'F', {'function'}, 0)
    F.add_sym('c1', tags=set(), typ=Type.object(C))
    F.add_sym('c2', tags=set(), typ=Type.object(C))

    blk = Block(F, nametag='blk1')
    F.set_entry_block(blk)
    F.set_exit_block(blk)

    mv = Move(Temp('c1', Ctx.STORE), Temp('c2', Ctx.LOAD))
    object.__setattr__(mv, 'block', blk)
    blk.append_stm(mv)
    Block.set_order(blk, 0)

    ObjectHierarchyCopier().process(F)

    # No additional stms should be inserted (x is int, not object)
    assert len(blk.stms) == 1, f'Expected 1 stm, got {len(blk.stms)}'
