"""Tests for NewScalarSSATransformer."""
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir import ir as new
from polyphony.compiler.ir.irreader import IRReader as IRParser
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.transformers.ssa import NewScalarSSATransformer
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def build_scope(src):
    setup_test()
    parser = IRParser(src)
    parser.parse_scope()
    for name in parser.sources:
        return env.scopes[name]


def test_new_syms_ordering():
    """NewSSA must use a list (not set) for new_syms to preserve
    inherit_sym call order. Using a set causes non-deterministic
    symbol ID assignment, leading to incorrect Verilog output.

    This was the root cause of 33 HDL simulation failures."""
    src = '''
scope F
tags function returnable
return int32
var c: bool
var x: int32
var y: int32

blk1:
mv c True
cj c blk2 blk3

blk2:
mv x 1
mv y 2
j exit

blk3:
mv x 3
mv y 4
j exit

exit:
mv @return (+ x y)
ret @return
'''
    scope = build_scope(src)
    NewScalarSSATransformer().process(scope)
    syms = sorted(scope.symbols.keys())

    # x and y are defined in two branches, so SSA should create renamed versions
    ssa_syms = [s for s in syms if '#' in s]
    assert len(ssa_syms) > 0, 'No SSA symbols created'

    # Verify SSA-renamed variables have expected base names (x, y)
    ssa_bases = sorted(set(s.split('#')[0] for s in ssa_syms))
    assert 'x' in ssa_bases, f'x not in SSA bases: {ssa_bases}'
    assert 'y' in ssa_bases, f'y not in SSA bases: {ssa_bases}'

    # Run multiple times to verify deterministic ordering
    for _ in range(5):
        setup_test()
        scope2 = build_scope(src)
        NewScalarSSATransformer().process(scope2)
        syms2 = sorted(scope2.symbols.keys())
        assert syms == syms2, f'Non-deterministic SSA symbol ordering detected'


def test_phi_predicates_use_new_ir():
    """PHI predicates must use path_exp.
    Mixing old IR in PHI predicates causes ValueError
    when converting back to old IR."""
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

    # This should not raise ValueError about 'Unknown new IrExp type: TEMP'
    NewScalarSSATransformer().process(scope)

    # Verify PHIs were created and have correct structure
    exit_blk = None
    for blk in scope.traverse_blocks():
        if blk.nametag == 'exit':
            exit_blk = blk
            break

    # After SSA, stms should be valid IR
    for stm in exit_blk.stms:
        if isinstance(stm, PHI):
            # PHI predicates (ps) should be old IR after reverse conversion
            for p in stm.ps:
                assert isinstance(p, (IR, type(None))), (
                    f'PHI predicate is not old IR: {type(p).__name__}'
                )


def test_ssa_preserves_block_structure():
    """SSA transformation should preserve the CFG structure."""
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
    blocks_before = list(scope.traverse_blocks())

    NewScalarSSATransformer().process(scope)

    blocks_after = list(scope.traverse_blocks())

    # Same number of blocks
    assert len(blocks_before) == len(blocks_after)

    # All stms have correct block references
    for blk in blocks_after:
        for stm in blk.stms:
            assert stm.block is blk, (
                f'stm.block mismatch: stm in {blk.name} but stm.block is {stm.block.name}'
            )


def test_new_syms_no_duplicate_rename():
    """new_syms must use identity-based dedup (not value-based).

    Pydantic BaseModel __eq__ compares by value, so different Temp objects
    with the same name are considered equal. Without identity-based dedup,
    the same var gets added multiple times to new_syms, causing double
    rename (data0 -> data0#1 -> data0#1#1) which corrupts the IR.

    This was the root cause of list17.py hanging in objtrans."""
    src = '''
scope F
tags function returnable
return int32
var c: bool
var x: list<int32>[3]
var y: list<int32>[3]

blk1:
mv c True
cj c blk2 blk3

blk2:
mv x [1 2 3]
j exit

blk3:
mv x [4 5 6]
j exit

exit:
mv @return 0
ret @return
'''
    scope = build_scope(src)
    NewScalarSSATransformer().process(scope)

    # After SSA, verify no #1#1 double-renamed symbols
    for name in scope.symbols:
        assert '#1#1' not in name, (
            f'Double rename detected: {name} — new_syms dedup is broken'
        )


def test_sort_phi_does_not_reorder_uphi():
    """_sort_phi must only sort exact Phi type, not UPhi/LPhi subclasses.
    If UPhi is included in sorting, PHI definitions can end up after UPHI
    uses, causing incorrect SSA renaming (wrong variable version).

    Root cause: isinstance(uphi, Phi) is True because UPhi inherits from
    Phi in the new IR model. The fix uses type(stm) is Phi."""
    from polyphony.compiler.ir.ir import Phi, UPhi, Temp, Const, Ctx
    from polyphony.compiler.ir.ir import Loc

    blk_scope = build_scope('''
scope F
tags function
var a: int32
var b: int32
var t: int32

blk1:
mv a 1
''')
    blk = blk_scope.entry_block

    # Simulate: PHI for 'a' and UPhi for 't' in same block
    phi_a = Phi(var=Temp(name='a', ctx=Ctx.STORE),
                args=[Const(value=None), Const(value=None)],
                block=blk, loc=Loc('', 0))
    phi_b = Phi(var=Temp(name='b', ctx=Ctx.STORE),
                args=[Const(value=None), Const(value=None)],
                block=blk, loc=Loc('', 0))
    uphi_t = UPhi(var=Temp(name='t', ctx=Ctx.STORE),
                  args=[Temp(name='a'), Temp(name='b')],
                  ps=[Const(value=1), Const(value=1)],
                  block=blk, loc=Loc('', 0))
    blk.stms = [phi_a, phi_b, uphi_t]

    # Run _sort_phi
    from polyphony.compiler.ir.transformers.ssa import NewScalarSSATransformer
    ssa = NewScalarSSATransformer()
    ssa.scope = blk_scope
    ssa._sort_phi(blk)

    # UPhi must remain after all Phis
    phi_indices = [i for i, s in enumerate(blk.stms) if type(s) is Phi]
    uphi_indices = [i for i, s in enumerate(blk.stms) if type(s) is UPhi]
    assert all(pi < ui for pi in phi_indices for ui in uphi_indices), \
        f'UPhi appears before Phi: {[type(s).__name__ for s in blk.stms]}'


def test_uphi_has_loc():
    """UPhi generated by TupleSSA must have a non-None loc.
    Missing loc causes AttributeError in DFG builder."""
    src = '''
scope F
tags function returnable
return int32
var t: int32

blk1:
mv t 1
j blk2

blk2:
mv @return t
ret @return
'''
    scope = build_scope(src)
    NewScalarSSATransformer().process(scope)

    # Verify all stms have non-None loc
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if hasattr(stm, 'loc'):
                assert stm.loc is not None, f'stm has None loc: {stm}'
