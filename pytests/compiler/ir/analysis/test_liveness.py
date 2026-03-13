from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir.irreader import IRReader as IRParser
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.analysis.liveness import Liveness
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def build_scope(src):
    parser = IRParser(src)
    parser.parse_scope()
    for name in parser.sources:
        return env.scopes[name]


def blk_by_name(scope, suffix):
    for blk in scope.traverse_blocks():
        if blk.nametag == suffix:
            return blk
    raise ValueError(f'Block {suffix} not found')


def livein_names(liveness, blk):
    """Return set of symbol names that are live-in at blk."""
    return {sym.name for sym, _ in liveness.liveins[blk]}


def liveout_names(liveness, blk):
    """Return set of symbol names that are live-out at blk."""
    return {sym.name for sym, _ in liveness.liveouts[blk]}


def test_simple_def_use():
    """x defined in blk1, used in blk2. x is live-out of blk1, live-in of blk2."""
    setup_test()
    src = '''
scope F
tags function
var x: int32
var y: int32

blk1:
mv x 1
j blk2

blk2:
mv y x
'''
    scope = build_scope(src)
    liveness = Liveness()
    liveness.process(scope)

    blk1 = blk_by_name(scope, 'blk1')
    blk2 = blk_by_name(scope, 'blk2')

    assert 'x' in liveout_names(liveness, blk1)
    assert 'x' in livein_names(liveness, blk2)


def test_def_use_same_block():
    """x defined and used in the same block. x is live-out (def block = use block)."""
    setup_test()
    src = '''
scope F
tags function
var x: int32
var y: int32

blk1:
mv x 1
mv y x
'''
    scope = build_scope(src)
    liveness = Liveness()
    liveness.process(scope)

    blk1 = blk_by_name(scope, 'blk1')
    # x is defined and used in the same block
    # liveness traces from def-block to use-block, so x appears in liveouts of blk1
    assert 'x' in liveout_names(liveness, blk1)


def test_diamond_liveness():
    """x defined in blk1, used in exit via both branches."""
    setup_test()
    src = '''
scope F
tags function returnable
return int32
var c: bool
var x: int32

blk1:
mv x 10
mv c True
cj c blk2 blk3

blk2:
mv @return x
j exit

blk3:
mv @return x
j exit

exit:
ret @return
'''
    scope = build_scope(src)
    liveness = Liveness()
    liveness.process(scope)

    blk1 = blk_by_name(scope, 'blk1')
    blk2 = blk_by_name(scope, 'blk2')
    blk3 = blk_by_name(scope, 'blk3')

    # x is live-out of blk1 (defined there, used in blk2 and blk3)
    assert 'x' in liveout_names(liveness, blk1)
    # x is live-in of blk2 and blk3
    assert 'x' in livein_names(liveness, blk2)
    assert 'x' in livein_names(liveness, blk3)


def test_no_liveness_for_dead_var():
    """z is defined but never used. It should not appear in any livein/liveout."""
    setup_test()
    src = '''
scope F
tags function
var x: int32
var z: int32

blk1:
mv x 1
mv z 99
j blk2

blk2:
mv x (+ x 1)
'''
    scope = build_scope(src)
    liveness = Liveness()
    liveness.process(scope)

    blk1 = blk_by_name(scope, 'blk1')
    blk2 = blk_by_name(scope, 'blk2')

    # z is never used, so it should not be live anywhere
    assert 'z' not in liveout_names(liveness, blk1)
    assert 'z' not in livein_names(liveness, blk2)


def test_pass_through_block():
    """x defined in blk1, used in blk3. blk2 is a pass-through.
    x should be live-in and live-out of blk2."""
    setup_test()
    src = '''
scope F
tags function
var x: int32
var y: int32

blk1:
mv x 1
j blk2

blk2:
mv y 2
j blk3

blk3:
mv y x
'''
    scope = build_scope(src)
    liveness = Liveness()
    liveness.process(scope)

    blk1 = blk_by_name(scope, 'blk1')
    blk2 = blk_by_name(scope, 'blk2')
    blk3 = blk_by_name(scope, 'blk3')

    assert 'x' in liveout_names(liveness, blk1)
    assert 'x' in livein_names(liveness, blk2)
    assert 'x' in liveout_names(liveness, blk2)
    assert 'x' in livein_names(liveness, blk3)


def test_multiple_defs_different_blocks():
    """x defined in blk2 and blk3 (diamond), used in exit.
    x should be live-out of blk2 and blk3, live-in of exit."""
    setup_test()
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
mv @return x
ret @return
'''
    scope = build_scope(src)
    liveness = Liveness()
    liveness.process(scope)

    blk2 = blk_by_name(scope, 'blk2')
    blk3 = blk_by_name(scope, 'blk3')
    exit_blk = blk_by_name(scope, 'exit')

    assert 'x' in liveout_names(liveness, blk2)
    assert 'x' in liveout_names(liveness, blk3)
    assert 'x' in livein_names(liveness, exit_blk)
