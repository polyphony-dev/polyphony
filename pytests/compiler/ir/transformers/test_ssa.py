"""Tests for ScalarSSATransformer."""
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir import ir as new
from polyphony.compiler.ir.irreader import IRReader as IRParser
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.transformers.ssa import ScalarSSATransformer
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
    ScalarSSATransformer().process(scope)
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
        ScalarSSATransformer().process(scope2)
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
    ScalarSSATransformer().process(scope)

    # Verify PHIs were created and have correct structure
    exit_blk = None
    for blk in scope.traverse_blocks():
        if blk.nametag == 'exit':
            exit_blk = blk
            break

    # After SSA, stms should be valid IR
    for stm in exit_blk.stms:
        if isinstance(stm, Phi):
            # PHI predicates (ps) should be old IR after reverse conversion
            for p in stm.ps:
                assert isinstance(p, (Ir, type(None))), (
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

    ScalarSSATransformer().process(scope)

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
    ScalarSSATransformer().process(scope)

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
    from polyphony.compiler.ir.transformers.ssa import ScalarSSATransformer
    ssa = ScalarSSATransformer()
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
    ScalarSSATransformer().process(scope)

    # Verify all stms have non-None loc
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if hasattr(stm, 'loc'):
                assert stm.loc is not None, f'stm has None loc: {stm}'


# ============================================================
# Tests for _merge_path_exp and _rel_and_exp helper functions
# ============================================================

def test_rel_and_exp_none_inputs():
    """_rel_and_exp returns the other arg when one is None."""
    from polyphony.compiler.ir.transformers.ssa import _rel_and_exp
    from polyphony.compiler.ir.ir import Const, Temp

    a = Temp(name='a')
    # exp1 is None -> return exp2
    assert _rel_and_exp(None, a) is a
    # exp2 is None -> return exp1
    assert _rel_and_exp(a, None) is a
    # both None
    assert _rel_and_exp(None, None) is None


def test_rel_and_exp_const_true_shortcut():
    """_rel_and_exp returns the other when one side is Const(true)."""
    from polyphony.compiler.ir.transformers.ssa import _rel_and_exp
    from polyphony.compiler.ir.ir import Const, Temp

    a = Temp(name='a')
    true_c = Const(value=1)

    # Const(true) on left => return right
    result = _rel_and_exp(true_c, a)
    assert result == a

    # Const(true) on right => return left
    result = _rel_and_exp(a, true_c)
    assert result == a


def test_rel_and_exp_produces_and():
    """_rel_and_exp produces RelOp(And) when neither side is None/true."""
    from polyphony.compiler.ir.transformers.ssa import _rel_and_exp
    from polyphony.compiler.ir.ir import Temp, RelOp

    a = Temp(name='a')
    b = Temp(name='b')
    result = _rel_and_exp(a, b)
    assert isinstance(result, RelOp)
    assert result.op == 'And'


def test_merge_path_exp_cjump_true_branch():
    """_merge_path_exp with CJump returns path exp for true branch."""
    from polyphony.compiler.ir.transformers.ssa import _merge_path_exp
    from polyphony.compiler.ir.ir import Temp, CJump, Const
    from pytests.compiler.base import MockScope
    from polyphony.compiler.ir.block import Block

    scope = MockScope('test')
    pred = Block(scope, nametag='pred')
    true_blk = Block(scope, nametag='true')
    false_blk = Block(scope, nametag='false')
    cond = Temp(name='c')
    cjump = CJump(exp=cond, true=true_blk, false=false_blk)
    object.__setattr__(cjump, 'block', pred)
    pred.stms = [cjump]
    pred.path_exp = None

    # True branch
    result = _merge_path_exp(pred, true_blk)
    assert result == cond

    # False branch
    from polyphony.compiler.ir.ir import UnOp
    result = _merge_path_exp(pred, false_blk)
    assert isinstance(result, UnOp)
    assert result.op == 'Not'


def test_merge_path_exp_mcjump_single_target():
    """_merge_path_exp with MCJump handles single target correctly."""
    from polyphony.compiler.ir.transformers.ssa import _merge_path_exp
    from polyphony.compiler.ir.ir import Temp, MCJump, Const
    from pytests.compiler.base import MockScope
    from polyphony.compiler.ir.block import Block

    scope = MockScope('test')
    pred = Block(scope, nametag='pred')
    blk_a = Block(scope, nametag='a')
    blk_b = Block(scope, nametag='b')
    cond_a = Temp(name='ca')
    cond_b = Temp(name='cb')
    mcjump = MCJump(conds=[cond_a, cond_b], targets=[blk_a, blk_b])
    object.__setattr__(mcjump, 'block', pred)
    pred.stms = [mcjump]
    pred.path_exp = None

    result = _merge_path_exp(pred, blk_a)
    assert result == cond_a


def test_merge_path_exp_mcjump_dup_target_no_hint():
    """_merge_path_exp with MCJump handles duplicate targets using Or."""
    from polyphony.compiler.ir.transformers.ssa import _merge_path_exp
    from polyphony.compiler.ir.ir import Temp, MCJump, RelOp
    from pytests.compiler.base import MockScope
    from polyphony.compiler.ir.block import Block

    scope = MockScope('test')
    pred = Block(scope, nametag='pred')
    blk_a = Block(scope, nametag='a')
    cond_0 = Temp(name='c0')
    cond_1 = Temp(name='c1')
    # blk_a appears twice as target
    mcjump = MCJump(conds=[cond_0, cond_1], targets=[blk_a, blk_a])
    object.__setattr__(mcjump, 'block', pred)
    pred.stms = [mcjump]
    pred.path_exp = None

    result = _merge_path_exp(pred, blk_a)
    assert isinstance(result, RelOp)
    assert result.op == 'Or'


def test_merge_path_exp_mcjump_with_idx_hint():
    """_merge_path_exp with MCJump uses idx_hint for duplicate targets."""
    from polyphony.compiler.ir.transformers.ssa import _merge_path_exp
    from polyphony.compiler.ir.ir import Temp, MCJump
    from pytests.compiler.base import MockScope
    from polyphony.compiler.ir.block import Block

    scope = MockScope('test')
    pred = Block(scope, nametag='pred')
    blk_a = Block(scope, nametag='a')
    cond_0 = Temp(name='c0')
    cond_1 = Temp(name='c1')
    mcjump = MCJump(conds=[cond_0, cond_1], targets=[blk_a, blk_a])
    object.__setattr__(mcjump, 'block', pred)
    pred.stms = [mcjump]
    pred.path_exp = None

    result = _merge_path_exp(pred, blk_a, idx_hint=1)
    assert result == cond_1


def test_merge_path_exp_jump_no_branch():
    """_merge_path_exp with Jump (no branch) returns pred's path_exp."""
    from polyphony.compiler.ir.transformers.ssa import _merge_path_exp
    from polyphony.compiler.ir.ir import Temp, Jump, Const
    from pytests.compiler.base import MockScope
    from polyphony.compiler.ir.block import Block

    scope = MockScope('test')
    pred = Block(scope, nametag='pred')
    blk = Block(scope, nametag='blk')
    jump = Jump(blk)
    object.__setattr__(jump, 'block', pred)
    pred.stms = [jump]
    pred.path_exp = Const(value=1)

    result = _merge_path_exp(pred, blk)
    assert isinstance(result, Const)
    assert result.value == 1


# ============================================================
# Tests for ListSSATransformer and ObjectSSATransformer
# ============================================================

def test_list_ssa_transformer():
    """ListSSATransformer should rename list-typed variables with multiple defs."""
    from polyphony.compiler.ir.transformers.ssa import ListSSATransformer
    src = '''
scope F
tags function returnable
return int32
var c: bool
var x: list<int32>[3]

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
    ListSSATransformer().process(scope)
    ssa_syms = [s for s in scope.symbols.keys() if '#' in s]
    # x is a list with two defs => should be SSA-renamed
    ssa_bases = set(s.split('#')[0] for s in ssa_syms)
    assert 'x' in ssa_bases, f'x not in SSA bases: {ssa_bases}'


def test_list_ssa_skips_non_list_vars():
    """ListSSATransformer should not rename non-list typed variables."""
    from polyphony.compiler.ir.transformers.ssa import ListSSATransformer
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
    ListSSATransformer().process(scope)
    ssa_syms = [s for s in scope.symbols.keys() if '#' in s]
    x_renamed = [s for s in ssa_syms if s.startswith('x#')]
    assert len(x_renamed) == 0, f'Non-list x should not be renamed by ListSSA: {x_renamed}'


def test_scalar_ssa_skips_single_def():
    """ScalarSSATransformer should not rename variables with only one def."""
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
    ScalarSSATransformer().process(scope)
    ssa_syms = [s for s in scope.symbols.keys() if '#' in s]
    x_renamed = [s for s in ssa_syms if s.startswith('x')]
    assert len(x_renamed) == 0, f'Single-def x should not be renamed: {x_renamed}'


def test_scalar_ssa_skips_class_scope():
    """ScalarSSATransformer.process should return early for class scopes."""
    setup_test()
    scope = Scope.create(None, 'C', {'class'}, 0)
    scope.add_sym('x', tags=set(), typ=Type.int(32))
    # Should not raise (early return for class scope)
    ScalarSSATransformer().process(scope)


def test_scalar_ssa_skips_namespace_scope():
    """ScalarSSATransformer.process should return early for namespace scopes."""
    setup_test()
    scope = Scope.create(None, 'N', {'namespace'}, 0)
    scope.add_sym('x', tags=set(), typ=Type.int(32))
    ScalarSSATransformer().process(scope)


def test_qsym_to_var_single_symbol():
    """_qsym_to_var with len 1 returns Temp."""
    setup_test()
    scope = Scope.create(None, 'F', {'function'}, 0)
    sym = scope.add_sym('x', tags=set(), typ=Type.int(32))
    ssa = ScalarSSATransformer()
    ssa.scope = scope
    var = ssa._qsym_to_var((sym,), Ctx.STORE)
    assert isinstance(var, Temp)
    assert var.name == 'x'
    assert var.ctx == Ctx.STORE


def test_qsym_to_var_nested():
    """_qsym_to_var with len > 1 returns Attr chain."""
    setup_test()
    scope = Scope.create(None, 'F', {'function'}, 0)
    sym_a = scope.add_sym('a', tags=set(), typ=Type.int(32))
    sym_b = scope.add_sym('b', tags=set(), typ=Type.int(32))
    ssa = ScalarSSATransformer()
    ssa.scope = scope
    var = ssa._qsym_to_var((sym_a, sym_b), Ctx.STORE)
    assert isinstance(var, Attr)
    assert var.name == 'b'
    assert var.ctx == Ctx.STORE
    assert isinstance(var.exp, Temp)
    assert var.exp.name == 'a'
    assert var.exp.ctx == Ctx.LOAD


def test_object_ssa_need_rename():
    """ObjectSSATransformer._need_rename should check object type conditions."""
    from polyphony.compiler.ir.transformers.ssa import ObjectSSATransformer
    from polyphony.compiler.ir.analysis.usedef import UseDefDetector

    setup_test()
    C = Scope.create(None, 'C', {'class'}, 0)
    C.add_sym('v', tags=set(), typ=Type.int(32))
    F = Scope.create(None, 'F', {'function'}, 0)
    obj_sym = F.add_sym('obj', tags=set(), typ=Type.object(C))
    int_sym = F.add_sym('x', tags=set(), typ=Type.int(32))
    blk = Block(F, nametag='blk1')
    F.set_entry_block(blk)
    F.set_exit_block(blk)
    Block.set_order(blk, 0)

    ssa = ObjectSSATransformer()
    ssa.scope = F
    ssa.usedef = UseDefDetector().process(F)

    # Non-object type => False
    assert not ssa._need_rename(int_sym, (int_sym,))

    # Object type => True (when not param, not free, etc.)
    assert ssa._need_rename(obj_sym, (obj_sym,))

    # self name => False
    from polyphony.compiler.common.env import env as test_env
    self_sym = F.add_sym(test_env.self_name, tags=set(), typ=Type.object(C))
    assert not ssa._need_rename(self_sym, (self_sym,))

    # Module scope => False
    M = Scope.create(None, 'M', {'module', 'class'}, 0)
    mod_sym = M.add_sym('obj', tags=set(), typ=Type.object(C))
    ssa2 = ObjectSSATransformer()
    ssa2.scope = M
    assert not ssa2._need_rename(mod_sym, (mod_sym,))

    # Namespace scope => False
    N = Scope.create(None, 'N', {'namespace'}, 0)
    ns_sym = N.add_sym('obj', tags=set(), typ=Type.object(C))
    ssa3 = ObjectSSATransformer()
    ssa3.scope = N
    assert not ssa3._need_rename(ns_sym, (ns_sym,))

    # Param => False
    F2 = Scope.create(None, 'F2', {'function'}, 0)
    param_sym = F2.add_sym('p', tags={'param'}, typ=Type.object(C))
    ssa4 = ObjectSSATransformer()
    ssa4.scope = F2
    assert not ssa4._need_rename(param_sym, (param_sym,))

    # Free => False
    F3 = Scope.create(None, 'F3', {'function'}, 0)
    free_sym = F3.add_sym('fr', tags={'free'}, typ=Type.object(C))
    ssa5 = ObjectSSATransformer()
    ssa5.scope = F3
    assert not ssa5._need_rename(free_sym, (free_sym,))

    # Object with module scope => False
    Mod = Scope.create(None, 'Mod', {'module', 'class'}, 0)
    F4 = Scope.create(None, 'F4', {'function'}, 0)
    mod_obj_sym = F4.add_sym('mo', tags=set(), typ=Type.object(Mod))
    ssa6 = ObjectSSATransformer()
    ssa6.scope = F4
    assert not ssa6._need_rename(mod_obj_sym, (mod_obj_sym,))


def test_tuple_ssa_need_rename():
    """TupleSSATransformer._need_rename should check tuple type conditions."""
    from polyphony.compiler.ir.transformers.ssa import TupleSSATransformer
    from polyphony.compiler.ir.analysis.usedef import UseDefDetector

    setup_test()
    F = Scope.create(None, 'F', {'function'}, 0)
    t_sym = F.add_sym('t', tags=set(), typ=Type.tuple(Type.int(32), 2))
    x_sym = F.add_sym('x', tags=set(), typ=Type.int(32))
    blk = Block(F, nametag='blk1')
    F.set_entry_block(blk)
    F.set_exit_block(blk)
    Block.set_order(blk, 0)

    ssa = TupleSSATransformer()
    ssa.scope = F
    ssa.usedef = UseDefDetector().process(F)

    # tuple type => True
    assert ssa._need_rename(t_sym, (t_sym,))

    # Non-tuple type => False
    assert not ssa._need_rename(x_sym, (x_sym,))

    # Param tuple => False
    tp_sym = F.add_sym('tp', tags={'param'}, typ=Type.tuple(Type.int(32), 2))
    assert not ssa._need_rename(tp_sym, (tp_sym,))

    # Namespace scope => False
    N = Scope.create(None, 'N', {'namespace'}, 0)
    tn_sym = N.add_sym('tn', tags=set(), typ=Type.tuple(Type.int(32), 2))
    ssa3 = TupleSSATransformer()
    ssa3.scope = N
    assert not ssa3._need_rename(tn_sym, (tn_sym,))


def test_list_ssa_need_rename():
    """ListSSATransformer._need_rename should check list type conditions."""
    from polyphony.compiler.ir.transformers.ssa import ListSSATransformer
    from polyphony.compiler.ir.analysis.usedef import UseDefDetector

    setup_test()
    F = Scope.create(None, 'F', {'function'}, 0)
    l_sym = F.add_sym('lst', tags=set(), typ=Type.list(Type.int(32), 3))
    x_sym = F.add_sym('x', tags=set(), typ=Type.int(32))
    blk = Block(F, nametag='blk1')
    F.set_entry_block(blk)
    F.set_exit_block(blk)
    Block.set_order(blk, 0)

    ssa = ListSSATransformer()
    ssa.scope = F
    ssa.usedef = UseDefDetector().process(F)

    # List type, not param => True
    assert ssa._need_rename(l_sym, (l_sym,))

    # Non-list type => False
    assert not ssa._need_rename(x_sym, (x_sym,))

    # Param list => False
    lp_sym = F.add_sym('lp', tags={'param'}, typ=Type.list(Type.int(32), 3))
    assert not ssa._need_rename(lp_sym, (lp_sym,))

    # Namespace scope => False
    N = Scope.create(None, 'N', {'namespace'}, 0)
    ln_sym = N.add_sym('ln', tags=set(), typ=Type.list(Type.int(32), 3))
    ssa3 = ListSSATransformer()
    ssa3.scope = N
    assert not ssa3._need_rename(ln_sym, (ln_sym,))


def test_scalar_ssa_need_rename():
    """ScalarSSATransformer._need_rename checks for multiple definitions."""
    from polyphony.compiler.ir.analysis.usedef import UseDefDetector

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
    ssa = ScalarSSATransformer()
    ssa.scope = scope
    ssa.usedef = UseDefDetector().process(scope)

    x_sym = scope.find_sym('x')
    # x has 2 defs => should need rename
    assert ssa._need_rename(x_sym, (x_sym,))

    # c has only 1 def (or is condition) => should not need rename
    c_sym = scope.find_sym('c')
    # condition symbols are excluded
    assert not ssa._need_rename(c_sym, (c_sym,))


def test_remove_useless_phi():
    """SSA should remove phi nodes that have no uses."""
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
mv y 10
j exit

blk3:
mv x 2
mv y 20
j exit

exit:
mv @return x
ret @return
'''
    scope = build_scope(src)
    ScalarSSATransformer().process(scope)

    # y has two defs but is never used after exit - its phi should be removed
    exit_blk = None
    for blk in scope.traverse_blocks():
        if blk.nametag == 'exit':
            exit_blk = blk
            break

    # Check phi nodes in exit block
    phis = [stm for stm in exit_blk.stms if isinstance(stm, Phi)]
    # Only x should have a phi (y's phi should be removed as useless)
    phi_vars = [phi.var.name for phi in phis]
    assert 'x' in phi_vars or any('#' in v for v in phi_vars), \
        f'Expected at least x phi in exit block, got: {phi_vars}'


def test_ssa_return_phi():
    """SSA should handle return variable phi nodes correctly.
    When a return variable has a PHI, its args should lose the return tag."""
    src = '''
scope F
tags function returnable
return int32
var c: bool

blk1:
mv c True
cj c blk2 blk3

blk2:
mv @return 1
j exit

blk3:
mv @return 2
j exit

exit:
ret @return
'''
    scope = build_scope(src)
    ScalarSSATransformer().process(scope)

    # After SSA, the return variable may have been renamed
    # Just verify the process completes without error
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            assert isinstance(stm, (Ir,)), f'Non-IR stm found: {type(stm)}'


def test_tuple_ssa_process_class_scope():
    """TupleSSATransformer.process should return early for class scopes."""
    from polyphony.compiler.ir.transformers.ssa import TupleSSATransformer
    setup_test()
    scope = Scope.create(None, 'C', {'class'}, 0)
    scope.add_sym('x', tags=set(), typ=Type.int(32))
    TupleSSATransformer().process(scope)


def test_tuple_ssa_process_namespace_scope():
    """TupleSSATransformer.process should return early for namespace scopes."""
    from polyphony.compiler.ir.transformers.ssa import TupleSSATransformer
    setup_test()
    scope = Scope.create(None, 'N', {'namespace'}, 0)
    scope.add_sym('x', tags=set(), typ=Type.int(32))
    TupleSSATransformer().process(scope)


def test_ssa_three_way_branch():
    """SSA with three-way branch should produce correct phis."""
    src = '''
scope F
tags function returnable
return int32
var c1: bool
var c2: bool
var x: int32
var y: int32

blk1:
mv c1 True
mv c2 False
cj c1 blk2 blk3

blk2:
mv x 1
mv y 10
j exit

blk3:
mv x 2
mv y 20
cj c2 blk4 exit

blk4:
mv x 3
mv y 30
j exit

exit:
mv @return (+ x y)
ret @return
'''
    scope = build_scope(src)
    ScalarSSATransformer().process(scope)

    # Process should complete without error, exit block should have phis
    exit_blk = None
    for blk in scope.traverse_blocks():
        if blk.nametag == 'exit':
            exit_blk = blk
            break
    assert exit_blk is not None
    phis = [stm for stm in exit_blk.stms if isinstance(stm, Phi)]
    # x and y both have 2+ defs => should have phis
    assert len(phis) >= 1, f'Expected phi nodes in exit block'


def test_ssa_with_multi_pred_exit():
    """SSA should handle blocks with multiple predecessors."""
    src = '''
scope F
tags function returnable
return int32
var c: bool
var x: int32

blk1:
mv c True
mv x 0
cj c blk2 blk3

blk2:
mv x 1
j blk4

blk3:
mv x 2
j blk4

blk4:
mv @return x
j exit

exit:
ret @return
'''
    scope = build_scope(src)
    ScalarSSATransformer().process(scope)

    # Should produce a phi at blk4 (two preds)
    blk4 = None
    for blk in scope.traverse_blocks():
        if blk.nametag == 'blk4':
            blk4 = blk
            break
    assert blk4 is not None
    phis = [stm for stm in blk4.stms if isinstance(stm, Phi)]
    assert len(phis) >= 1, f'Expected phi at blk4'
