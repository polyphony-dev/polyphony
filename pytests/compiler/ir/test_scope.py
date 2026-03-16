from polyphony.compiler.common.env import env
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir.ir import name2var as _v
from polyphony.compiler.ir import ir as new
from polyphony.compiler.ir.irreader import IRReader as IRParser, ir_stm
from polyphony.compiler.ir.irwriter import IRWriter
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.types.type import Type
from pytests.compiler.base import setup_test, install_builtins
import pytest

_writer = IRWriter()

def _stm_text(stm):
    """Format a statement (old or new IR) to text for comparison."""
    return _writer.write_stm(stm)


def test_Scope_find_sym():
    setup_test()
    top = env.scopes['@top']
    scope0 = Scope.create(top, 'scope0', set())
    scope1 = Scope.create(scope0, 'scope1', set())

    global_var = top.add_sym('GLOBAL_VAR', set(), Type.int())
    scope0_v = scope0.add_sym('v', set(), Type.int())
    scope0_w = scope0.add_sym('w', set(), Type.int())
    scope1_v = scope1.add_sym('v', set(), Type.int())

    assert scope1.find_sym('GLOBAL_VAR') is global_var
    assert scope0.find_sym('GLOBAL_VAR') is global_var
    assert scope1.find_sym('v') is scope1_v
    assert scope1.find_sym('w') is scope0_w
    assert scope0.find_sym('v') is scope0_v


def test_Scope_find_owner_scope():
    setup_test()
    top = env.scopes['@top']
    scope0 = Scope.create(top, 'scope0', set())
    scope1 = Scope.create(scope0, 'scope1', set())

    gvar = top.add_sym('GLOBAL_VAR', set(), Type.int())
    v0 = scope0.add_sym('v', set(), Type.int())
    w0 = scope0.add_sym('w', set(), Type.int())
    v1 = scope1.add_sym('v', set(), Type.int())
    scope1.import_sym(gvar)

    assert top.find_owner_scope(gvar) is top
    assert scope0.find_owner_scope(gvar) is top
    assert scope1.find_owner_scope(gvar) is scope1

    assert scope0.find_owner_scope(v0) is scope0
    assert scope0.find_owner_scope(w0) is scope0
    assert scope0.find_owner_scope(v1) is None

    assert scope1.find_owner_scope(v0) is scope0
    assert scope1.find_owner_scope(w0) is scope0
    assert scope1.find_owner_scope(v1) is scope1



def test_clone_function():
    setup_test()
    block_src = """
    scope @top.f
    tags function
    param a:int32
    return int32
    var x: int32

    blk1:
    mv a @in_a
    mv x (call g a)
    j blk2

    blk2:
    mv @return x
    ret @return

    scope @top.g
    tags function
    param x:int32
    return int32

    blk1:
    mv x @in_x
    mv @return x
    ret @return
    """

    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    top.add_sym('f', tags=set(), typ=Type.function('@top.f'))
    top.add_sym('g', tags=set(), typ=Type.function('@top.g'))

    f = env.scopes['@top.f']
    prefix = 'cloned'
    postfix = 'cloned'

    f_ = f.clone(prefix, postfix)

    f_clone = env.scopes['@top.cloned_f_cloned']
    assert f_clone is f_
    assert f_clone.parent is top
    assert f_clone.is_function()
    assert f_clone.origin is f
    assert f_clone.orig_name == '@top.f'

    new_sym = top.find_sym('cloned_f_cloned')
    assert new_sym
    assert new_sym.typ.is_function()
    assert new_sym.typ.scope is f_clone

    f_clone_a = f_clone.find_sym('a')
    assert f_clone_a
    f_clone_x = f_clone.find_sym('x')
    assert f_clone_x
    f_clone_ret = f_clone.find_sym('@return')
    assert f_clone_ret

    f_a = f.find_sym('a')
    f_x = f.find_sym('x')
    f_ret = f.find_sym('@return')
    assert f_clone_a is not f_a
    assert f_clone_x is not f_x
    assert f_clone_ret is not f_ret

    gen = f_clone.traverse_blocks()
    blk1 = next(gen)
    blk2 = next(gen)
    with pytest.raises(StopIteration) as e:
        next(gen)
    assert blk1.scope is f_clone
    assert blk2.scope is f_clone
    assert _stm_text(blk1.stms[0]) == 'mv a @in_a'
    assert _stm_text(blk1.stms[1]) == 'mv x (call g a)'
    assert isinstance(blk1.stms[2], Jump)
    assert blk1.stms[2].target is blk2
    assert _stm_text(blk2.stms[0]) == 'mv @return x'
    assert _stm_text(blk2.stms[1]) == 'ret @return'

    # Mutating the clone should not affect the original
    blk1.stms[1] = new.Move(dst=new.Temp(name='x', ctx=new.Ctx.STORE), src=new.Call(func=new.Temp(name='g'), args=[('', new.Const(value=1))]), block=blk1)

    gen = f.traverse_blocks()
    blk1_orig = next(gen)
    assert _stm_text(blk1_orig.stms[1]) == 'mv x (call g a)'


def test_recursive_clone():
    setup_test()
    block_src = """
    scope @top.f
    tags function
    param a:int32
    return int32
    var g: function(@top.f.g)
    var x: int32

    blk1:
    mv a @in_a
    mv x (call g a)
    j blk2

    blk2:
    mv @return x
    ret @return

    scope @top.f.g
    tags function
    param x:int32
    return int32

    blk1:
    mv x @in_x
    mv @return x
    ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    top.add_sym('f', tags=set(), typ=Type.function('@top.f'))

    f = env.scopes['@top.f']
    g = env.scopes['@top.f.g']
    prefix = 'cloned'
    postfix = 'cloned'
    f_ = f.clone(prefix, postfix, parent=f.parent, recursive=True)

    f_clone = env.scopes['@top.cloned_f_cloned']
    g_clone = env.scopes['@top.cloned_f_cloned.cloned_g_cloned']
    assert g_clone is not g
    assert g_clone.parent is f_clone
    assert g_clone.is_function()
    assert g_clone.origin is g
    assert g_clone.orig_name == '@top.f.g'

    new_g_sym = f_clone.find_sym('cloned_g_cloned')
    assert new_g_sym
    assert new_g_sym.typ.is_function()
    assert new_g_sym.typ.scope is g_clone

    assert f_clone.find_sym('g') is None

    gen = f_clone.traverse_blocks()
    blk1 = next(gen)
    blk2 = next(gen)
    assert _stm_text(blk1.stms[0]) == 'mv a @in_a'
    assert _stm_text(blk1.stms[1]) == 'mv x (call cloned_g_cloned a)'
    assert isinstance(blk1.stms[2], Jump)
    assert blk1.stms[2].target is blk2

    assert _stm_text(blk2.stms[0]) == 'mv @return x'
    assert _stm_text(blk2.stms[1]) == 'ret @return'

def test_legb():
    setup_test(with_global=False)
    block_src = """
    scope @top
    tags namespace
    var C: class(@top.C)
    var x: int32

    scope @top.C
    tags class
    var __init__: function(@top.C.__init__)
    var x: int16

    scope @top.C.__init__
    tags method
    """

    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    gx = top.find_sym('x')
    assert gx
    assert gx.typ.is_int()
    assert gx.typ.width == 32

    C = env.scopes['@top.C']
    assert C
    cx = C.find_sym('x')
    assert cx
    assert cx.typ.is_int()
    assert cx.typ.width == 16
    C_init = env.scopes['@top.C.__init__']
    assert C_init
    cix = C_init.find_sym('x')
    assert cix
    assert cix is gx
    assert cix is not cx


def test_instantiate_class():
    pass

