"""Tests for new IfTransformer (ir-based)."""
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir import ir as new
from polyphony.compiler.ir.transformers.iftransform import NewIfTransformer
from polyphony.compiler.ir.irreader import IRReader as IRParser
from polyphony.compiler.ir.irwriter import IRWriter
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def build_scope(src):
    setup_test()
    parser = IRParser(src)
    parser.parse_scope()
    for name in parser.sources:
        return env.scopes[name]


def test_no_cjump_unchanged():
    """Blocks without CJUMP should not be affected."""
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 1
j blk2

blk2:
mv x 2
'''
    scope = build_scope(src)
    writer = IRWriter()
    before = [writer.write_stm(s) for s in scope.entry_block.stms]

    NewIfTransformer().process(scope)

    after = [writer.write_stm(s) for s in scope.entry_block.stms]
    assert before == after


def test_simple_cjump_unchanged():
    """A single CJUMP (no chained else-if) should remain unchanged."""
    src = '''
scope F
tags function returnable
return int32
var c: bool
var x: int32

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
ret @return
'''
    scope = build_scope(src)
    blk1 = scope.entry_block

    NewIfTransformer().process(scope)

    # Still a CJUMP (not merged into MCJUMP because blk3 has >1 stm or not a CJUMP)
    last = blk1.stms[-1]
    assert isinstance(last, (CJUMP, new.CJump))


def test_chained_cjump_to_mcjump():
    """Chained if-elif-else should be merged into MCJUMP.

    CFG: blk1 -cj(c1)-> blk2 (then)
                      -> else1 -cj(c2)-> blk3 (then)
                                      -> blk4 (else/final)
    """
    setup_test()
    scope = Scope.create(None, 'F', {'function'}, 0)
    scope.add_sym('c1', tags=set(), typ=Type.bool())
    scope.add_sym('c2', tags=set(), typ=Type.bool())
    scope.add_sym('x', tags=set(), typ=Type.int(32))

    blk1 = Block(scope, nametag='blk1')
    blk2 = Block(scope, nametag='blk2')
    else1 = Block(scope, nametag='else1')
    blk3 = Block(scope, nametag='blk3')
    blk4 = Block(scope, nametag='blk4')

    scope.set_entry_block(blk1)
    scope.set_exit_block(blk4)

    # blk1: cj c1 blk2 else1 (new IR in stms, post-switchover)
    cj1 = new.CJump(exp=new.Temp(name='c1'), true=blk2, false=else1, block=blk1)
    blk1.stms.append(cj1)
    blk1.connect(blk2)
    blk1.connect(else1)

    # else1: cj c2 blk3 blk4  (single CJUMP — should be merged)
    cj2 = new.CJump(exp=new.Temp(name='c2'), true=blk3, false=blk4, block=else1)
    else1.stms.append(cj2)
    else1.connect(blk3)
    else1.connect(blk4)

    # blk2, blk3, blk4: simple
    mv2 = new.Move(dst=new.Temp(name='x', ctx=new.Ctx.STORE), src=new.Const(value=1), block=blk2)
    blk2.stms.append(mv2)
    mv3 = new.Move(dst=new.Temp(name='x', ctx=new.Ctx.STORE), src=new.Const(value=2), block=blk3)
    blk3.stms.append(mv3)
    mv4 = new.Move(dst=new.Temp(name='x', ctx=new.Ctx.STORE), src=new.Const(value=3), block=blk4)
    blk4.stms.append(mv4)

    Block.set_order(blk1, 0)

    # Run new IfTransformer via adapter
    NewIfTransformer().process(scope)

    # blk1 should now end with MCJUMP instead of CJUMP
    last = blk1.stms[-1]
    assert isinstance(last, (MCJUMP, new.MCJump)), f'Expected MCJUMP, got {type(last).__name__}'
    assert len(last.conds) == 3  # c1, c2, CONST(1)
    assert len(last.targets) == 3  # blk2, blk3, blk4

    # else1 should be emptied
    assert else1.stms == []

    # Verify targets
    assert last.targets[0] is blk2
    assert last.targets[1] is blk3
    assert last.targets[2] is blk4

    # Verify succs/preds
    assert blk2 in blk1.succs
    assert blk3 in blk1.succs
    assert blk4 in blk1.succs


