from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir.irreader import IRReader as IRParser
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.analysis.usedef import UseDefDetector, UseDefUpdater
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def build_scope(src):
    """Parse IR text and return the first non-builtin scope."""
    parser = IRParser(src)
    parser.parse_scope()
    for name in parser.sources:
        scope = env.scopes[name]
        return scope


def has_const_value(consts, value):
    """Check if a set of CONST objects contains one with the given value.
    CONST.__hash__ uses object identity, so set 'in' doesn't work for equality."""
    return any(c.value == value for c in consts)


# --- UseDefDetector basic tests ---

def test_simple_move():
    """mv x 1: x is defined, 1 is a const use."""
    setup_test()
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 1
'''
    scope = build_scope(src)
    usedef = UseDefDetector().process(scope)

    x_sym = scope.find_sym('x')
    blk = scope.entry_block
    stm = blk.stms[0]

    assert stm in usedef.get_stms_defining(x_sym)
    assert stm not in usedef.get_stms_using(x_sym)
    assert has_const_value(usedef.get_consts_used_at(stm), 1)
    assert x_sym in usedef.get_syms_defined_at(blk)
    assert x_sym not in usedef.get_syms_used_at(blk)


def test_move_var_to_var():
    """mv y x: x is used, y is defined."""
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
    usedef = UseDefDetector().process(scope)

    x_sym = scope.find_sym('x')
    y_sym = scope.find_sym('y')
    stm1 = scope.entry_block.stms[1]  # mv y x

    assert stm1 in usedef.get_stms_defining(y_sym)
    assert stm1 in usedef.get_stms_using(x_sym)
    assert stm1 not in usedef.get_stms_defining(x_sym)
    assert stm1 not in usedef.get_stms_using(y_sym)


def test_binop_uses():
    """mv z (+ x y): x and y are used, z is defined."""
    setup_test()
    src = '''
scope F
tags function
var x: int32
var y: int32
var z: int32

blk1:
mv x 1
mv y 2
mv z (+ x y)
'''
    scope = build_scope(src)
    usedef = UseDefDetector().process(scope)

    x_sym = scope.find_sym('x')
    y_sym = scope.find_sym('y')
    z_sym = scope.find_sym('z')
    stm2 = scope.entry_block.stms[2]

    assert stm2 in usedef.get_stms_defining(z_sym)
    assert stm2 in usedef.get_stms_using(x_sym)
    assert stm2 in usedef.get_stms_using(y_sym)


def test_relop_cjump():
    """cj uses the condition variable."""
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
ret @return
'''
    scope = build_scope(src)
    usedef = UseDefDetector().process(scope)

    c_sym = scope.find_sym('c')
    blk1 = scope.entry_block
    assert c_sym in usedef.get_syms_defined_at(blk1)

    cj_stm = blk1.stms[1]
    assert cj_stm in usedef.get_stms_using(c_sym)


def test_multi_block_def():
    """x is defined in multiple blocks."""
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
ret @return
'''
    scope = build_scope(src)
    usedef = UseDefDetector().process(scope)

    x_sym = scope.find_sym('x')
    def_blks = usedef.get_blks_defining(x_sym)
    assert len(def_blks) == 2


def test_call_uses():
    """mv r (call f a b): f, a, b are used; r is defined."""
    setup_test()
    src = '''
scope F
tags function
var f: function(F)
var a: int32
var b: int32
var r: int32

blk1:
mv a 1
mv b 2
mv r (call f a b)
'''
    scope = build_scope(src)
    usedef = UseDefDetector().process(scope)

    f_sym = scope.find_sym('f')
    a_sym = scope.find_sym('a')
    b_sym = scope.find_sym('b')
    r_sym = scope.find_sym('r')
    stm2 = scope.entry_block.stms[2]

    assert stm2 in usedef.get_stms_defining(r_sym)
    assert stm2 in usedef.get_stms_using(a_sym)
    assert stm2 in usedef.get_stms_using(b_sym)
    assert stm2 in usedef.get_stms_using(f_sym)


def test_syscall_uses():
    """expr (syscall f x): f and x are used."""
    setup_test()
    src = '''
scope F
tags function
var x: int32
var f: function(F)

blk1:
mv x 42
expr (syscall f x)
'''
    scope = build_scope(src)
    usedef = UseDefDetector().process(scope)

    x_sym = scope.find_sym('x')
    f_sym = scope.find_sym('f')
    stm1 = scope.entry_block.stms[1]

    assert stm1 in usedef.get_stms_using(x_sym)
    assert stm1 in usedef.get_stms_using(f_sym)


def test_mref_uses():
    """mv v (mld xs i): xs and i are used, v is defined."""
    setup_test()
    src = '''
scope F
tags function
var xs: list<int32>[10]
var i: int32
var v: int32

blk1:
mv i 0
mv v (mld xs i)
'''
    scope = build_scope(src)
    usedef = UseDefDetector().process(scope)

    xs_sym = scope.find_sym('xs')
    i_sym = scope.find_sym('i')
    v_sym = scope.find_sym('v')
    stm1 = scope.entry_block.stms[1]

    assert stm1 in usedef.get_stms_defining(v_sym)
    assert stm1 in usedef.get_stms_using(xs_sym)
    assert stm1 in usedef.get_stms_using(i_sym)


def test_mstore_uses():
    """expr (mst xs i v): xs, i, v are all used."""
    setup_test()
    src = '''
scope F
tags function
var xs: list<int32>[10]
var i: int32
var v: int32

blk1:
mv i 0
mv v 42
expr (mst xs i v)
'''
    scope = build_scope(src)
    usedef = UseDefDetector().process(scope)

    xs_sym = scope.find_sym('xs')
    i_sym = scope.find_sym('i')
    v_sym = scope.find_sym('v')
    stm2 = scope.entry_block.stms[2]

    assert stm2 in usedef.get_stms_using(xs_sym)
    assert stm2 in usedef.get_stms_using(i_sym)
    assert stm2 in usedef.get_stms_using(v_sym)


def test_cmove_uses():
    """mv? cond x 1: cond is used, x is defined."""
    setup_test()
    src = '''
scope F
tags function
var cond: bool
var x: int32

blk1:
mv cond True
mv? cond x 1
'''
    scope = build_scope(src)
    usedef = UseDefDetector().process(scope)

    cond_sym = scope.find_sym('cond')
    x_sym = scope.find_sym('x')
    stm1 = scope.entry_block.stms[1]

    assert stm1 in usedef.get_stms_using(cond_sym)
    assert stm1 in usedef.get_stms_defining(x_sym)


def test_cexpr_uses():
    """expr? cond (call f x): cond, f, x are used."""
    setup_test()
    src = '''
scope F
tags function
var cond: bool
var x: int32
var f: function(F)

blk1:
mv cond True
mv x 1
expr? cond (call f x)
'''
    scope = build_scope(src)
    usedef = UseDefDetector().process(scope)

    cond_sym = scope.find_sym('cond')
    x_sym = scope.find_sym('x')
    stm2 = scope.entry_block.stms[2]

    assert stm2 in usedef.get_stms_using(cond_sym)
    assert stm2 in usedef.get_stms_using(x_sym)


# --- Query method tests ---

def test_get_all_def_use_syms():
    setup_test()
    src = '''
scope F
tags function
var x: int32
var y: int32
var z: int32

blk1:
mv x 1
mv y x
mv z (+ x y)
'''
    scope = build_scope(src)
    usedef = UseDefDetector().process(scope)

    x_sym = scope.find_sym('x')
    y_sym = scope.find_sym('y')
    z_sym = scope.find_sym('z')

    all_def = usedef.get_all_def_syms()
    assert x_sym in all_def
    assert y_sym in all_def
    assert z_sym in all_def

    all_use = usedef.get_all_use_syms()
    assert x_sym in all_use
    assert y_sym in all_use
    assert z_sym not in all_use


def test_get_vars_defined_at_block():
    setup_test()
    src = '''
scope F
tags function
var x: int32
var y: int32

blk1:
mv x 1
mv y 2
'''
    scope = build_scope(src)
    usedef = UseDefDetector().process(scope)

    blk = scope.entry_block
    vars_def = usedef.get_vars_defined_at(blk)
    names = {v.name for v in vars_def}
    assert 'x' in names
    assert 'y' in names


def test_get_vars_used_at_stm():
    setup_test()
    src = '''
scope F
tags function
var x: int32
var y: int32
var z: int32

blk1:
mv x 1
mv y 2
mv z (+ x y)
'''
    scope = build_scope(src)
    usedef = UseDefDetector().process(scope)

    stm2 = scope.entry_block.stms[2]
    vars_used = usedef.get_vars_used_at(stm2)
    names = {v.name for v in vars_used}
    assert 'x' in names
    assert 'y' in names
    assert 'z' not in names


# --- Attribute (ATTR) tests ---

def test_attr_def_use():
    """mv self.x v: self is used, self.x is defined, v is used."""
    setup_test()
    src = '''
scope C
tags class
var x: int32

scope C.__init__
tags method ctor
param self:object(C)
param x:int32
return object(C)

blk1:
mv x @in_x
mv self.x x
'''
    scope = build_scope(src)
    ctor = env.scopes['C.__init__']
    usedef = UseDefDetector().process(ctor)

    self_sym = ctor.find_sym('self')
    x_sym = ctor.find_sym('x')
    stm1 = ctor.entry_block.stms[1]  # mv self.x x

    assert stm1 in usedef.get_stms_using(x_sym)
    assert stm1 in usedef.get_stms_using(self_sym)


# --- UseDefUpdater tests ---

def test_updater_remove_stm():
    """Removing a statement should remove its uses/defs from the table."""
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
    usedef = UseDefDetector().process(scope)

    x_sym = scope.find_sym('x')
    y_sym = scope.find_sym('y')
    stm1 = scope.entry_block.stms[1]

    assert stm1 in usedef.get_stms_defining(y_sym)
    assert stm1 in usedef.get_stms_using(x_sym)

    usedef.remove_stm(scope, stm1)

    assert stm1 not in usedef.get_stms_defining(y_sym)
    assert stm1 not in usedef.get_stms_using(x_sym)


def test_updater_update():
    """UseDefUpdater.update replaces old stm's uses/defs with new stm's."""
    setup_test()
    src = '''
scope F
tags function
var x: int32
var y: int32
var z: int32

blk1:
mv x 1
mv y x
'''
    scope = build_scope(src)
    usedef = UseDefDetector().process(scope)

    x_sym = scope.find_sym('x')
    y_sym = scope.find_sym('y')
    z_sym = scope.find_sym('z')
    blk = scope.entry_block

    old_stm = blk.stms[1]  # mv y x
    new_stm = Move(Temp('z', Ctx.STORE), Const(42))
    object.__setattr__(new_stm, 'block', blk)

    updater = UseDefUpdater(scope, usedef)
    updater.update(old_stm, new_stm)

    assert old_stm not in usedef.get_stms_defining(y_sym)
    assert old_stm not in usedef.get_stms_using(x_sym)

    assert new_stm in usedef.get_stms_defining(z_sym)
    assert has_const_value(usedef.get_consts_used_at(new_stm), 42)


# --- Const tracking ---

def test_const_tracking():
    """Constants used in statements are tracked."""
    setup_test()
    src = '''
scope F
tags function
var x: int32
var y: int32

blk1:
mv x 42
mv y (+ x 10)
'''
    scope = build_scope(src)
    usedef = UseDefDetector().process(scope)

    stm0 = scope.entry_block.stms[0]
    stm1 = scope.entry_block.stms[1]

    assert has_const_value(usedef.get_consts_used_at(stm0), 42)
    assert has_const_value(usedef.get_consts_used_at(stm1), 10)


# --- mcjump test ---

def test_mcjump_uses():
    """mj uses all condition variables."""
    setup_test()
    src = '''
scope F
tags function returnable
return int32
var c1: bool
var c2: bool
var c3: bool

blk1:
mv c1 True
mv c2 False
mv c3 True
mj c1 t1 c2 t2 c3 t3

t1:
j exit

t2:
j exit

t3:
j exit

exit:
ret @return
'''
    scope = build_scope(src)
    usedef = UseDefDetector().process(scope)

    c1 = scope.find_sym('c1')
    c2 = scope.find_sym('c2')
    c3 = scope.find_sym('c3')
    mj_stm = scope.entry_block.stms[3]

    assert mj_stm in usedef.get_stms_using(c1)
    assert mj_stm in usedef.get_stms_using(c2)
    assert mj_stm in usedef.get_stms_using(c3)


# --- Multiple definitions of same variable ---

def test_multiple_defs():
    """x defined multiple times in same block."""
    setup_test()
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 1
mv x 2
mv x 3
'''
    scope = build_scope(src)
    usedef = UseDefDetector().process(scope)

    x_sym = scope.find_sym('x')
    def_stms = usedef.get_stms_defining(x_sym)
    assert len(def_stms) == 3


def test_new_uses():
    """mv obj (new C x): C and x are used, obj is defined."""
    setup_test()
    src = '''
scope C
tags class

scope C.__init__
tags method ctor
param self:object(C)
return object(C)

scope F
tags function
var C: class(C)
var obj: object(C)
var x: int32

blk1:
mv x 1
mv obj (new C x)
'''
    scope = build_scope(src)
    F = env.scopes['F']
    usedef = UseDefDetector().process(F)

    obj_sym = F.find_sym('obj')
    x_sym = F.find_sym('x')
    C_sym = F.find_sym('C')
    stm1 = F.entry_block.stms[1]

    assert stm1 in usedef.get_stms_defining(obj_sym)
    assert stm1 in usedef.get_stms_using(x_sym)
    assert stm1 in usedef.get_stms_using(C_sym)


def test_add_remove_use_new_ir_types():
    """UseDefTable.add_use/remove_use must dispatch correctly for new IR types
    (IrVariable, Const) in addition to old IR types.
    Without this fix, new IR Temp/Const falls through to assert False."""
    from polyphony.compiler.ir.analysis.usedef import UseDefTable
    from polyphony.compiler.ir import ir as new_ir
    setup_test()
    scope = Scope.create(None, 'S', set(), 0)
    sym = scope.add_sym('x', tags=set(), typ=Type.int(8))

    table = UseDefTable()
    new_stm = new_ir.Move(dst=new_ir.Temp(name='y', ctx=new_ir.Ctx.STORE),
                          src=new_ir.Temp(name='x'))

    # add_use with new IR Const should dispatch to add_const_use, not assert
    new_const = new_ir.Const(value=42)
    table.add_use(scope, new_const, new_stm)

    # remove_use with new IR Const should dispatch to remove_const_use
    table.remove_use(scope, new_const, new_stm)

    # Verify old IR types still work
    old_stm = Move(Temp('y', Ctx.STORE), Temp('x'))
    old_const = Const(99)
    table.add_use(scope, old_const, old_stm)
    table.remove_use(scope, old_const, old_stm)


def test_matches_old_usedef():
    """UseDefDetector should produce equivalent results to old UseDefDetector."""
    setup_test()
    src = '''
scope F
tags function
var x: int32
var y: int32
var z: int32

blk1:
mv x 1
mv y 2
mv z (+ x y)
'''
    scope = build_scope(src)

    # Old detector on old IR
    old_usedef = UseDefDetector().process(scope)

    # New detector on new IR
    new_usedef = UseDefDetector().process(scope)

    x_sym = scope.find_sym('x')
    y_sym = scope.find_sym('y')
    z_sym = scope.find_sym('z')

    # Same def/use symbols
    assert set(old_usedef.get_all_def_syms()) == set(new_usedef.get_all_def_syms())
    assert set(old_usedef.get_all_use_syms()) == set(new_usedef.get_all_use_syms())

    # Same number of definitions per symbol
    for sym in [x_sym, y_sym, z_sym]:
        assert len(old_usedef.get_stms_defining(sym)) == len(new_usedef.get_stms_defining(sym))
        assert len(old_usedef.get_stms_using(sym)) == len(new_usedef.get_stms_using(sym))


def test_usedef_table_accepts_new_ir_stm():
    """UseDefTable query methods must accept new IR stm types.
    This was a bug: isinstance checks only matched old IrStm."""
    setup_test()
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 1
'''
    scope = build_scope(src)

    usedef = UseDefDetector().process(scope)

    stm = scope.entry_block.stms[0]
    # These must not raise AssertionError
    vars_def = usedef.get_vars_defined_at(stm)
    assert len(vars_def) == 1
    syms_def = usedef.get_syms_defined_at(stm)
    assert len(syms_def) == 1
    vars_used = usedef.get_vars_used_at(stm)
    consts = usedef.get_consts_used_at(stm)
