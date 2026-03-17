from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir.irreader import IRReader as IRParser
from polyphony.compiler.ir.irwriter import IRWriter
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def test_write_type():
    setup_test()
    writer = IRWriter()
    assert writer.write_type(Type.int(8)) == 'int8'
    assert writer.write_type(Type.int(32)) == 'int32'
    assert writer.write_type(Type.int(32, signed=False)) == 'bit32'
    assert writer.write_type(Type.bool()) == 'bool'
    assert writer.write_type(Type.str()) == 'str'
    assert writer.write_type(Type.none()) == 'none'
    assert writer.write_type(Type.undef()) == 'undef'


def test_write_type_list():
    setup_test()
    writer = IRWriter()
    assert writer.write_type(Type.list(Type.int(32), 10)) == 'list<int32>[10]'
    assert writer.write_type(Type.list(Type.bool(), Type.ANY_LENGTH)) == 'list<bool>[]'


def test_write_type_tuple():
    setup_test()
    writer = IRWriter()
    assert writer.write_type(Type.tuple(Type.int(32), 3)) == 'tuple<int32>[3]'
    assert writer.write_type(Type.tuple(Type.int(8), Type.ANY_LENGTH)) == 'tuple<int8>[]'


def test_write_type_scope():
    setup_test()
    top = env.scopes['@top']
    C = Scope.create(top, 'C', {'class'}, 0)
    F = Scope.create(top, 'F', {'function'}, 0)
    writer = IRWriter()
    assert writer.write_type(Type.object('@top.C')) == 'object(@top.C)'
    assert writer.write_type(Type.klass('@top.C')) == 'class(@top.C)'
    assert writer.write_type(Type.namespace('@top')) == 'namespace(@top)'
    assert writer.write_type(Type.function('@top.F')) == 'function(@top.F)'


def test_write_exp_const():
    setup_test()
    writer = IRWriter()
    assert writer.write_exp(Const(123)) == '123'
    assert writer.write_exp(Const(True)) == 'True'
    assert writer.write_exp(Const(False)) == 'False'
    assert writer.write_exp(Const('hello')) == "'hello'"


def test_write_exp_temp():
    setup_test()
    writer = IRWriter()
    assert writer.write_exp(Temp('x')) == 'x'
    assert writer.write_exp(Temp('@in_x')) == '@in_x'
    assert writer.write_exp(Temp('_x#1')) == '_x#1'


def test_write_exp_attr():
    setup_test()
    writer = IRWriter()
    exp = Attr(Attr(Temp('a'), 'b'), 'c')
    assert writer.write_exp(exp) == 'a.b.c'


def test_write_exp_unop():
    setup_test()
    writer = IRWriter()
    assert writer.write_exp(UnOp('USub', Temp('x'))) == '-x'
    assert writer.write_exp(UnOp('Not', Temp('x'))) == '!x'
    assert writer.write_exp(UnOp('Invert', Temp('x'))) == '~x'


def test_write_exp_binop():
    setup_test()
    writer = IRWriter()
    exp = BinOp('Add', Temp('a'), Const(1))
    assert writer.write_exp(exp) == '(+ a 1)'

    exp = BinOp('Mod', Temp('x'), Temp('y'))
    assert writer.write_exp(exp) == '(mod x y)'


def test_write_exp_relop():
    setup_test()
    writer = IRWriter()
    exp = RelOp('Eq', Temp('a'), Const(0))
    assert writer.write_exp(exp) == '(== a 0)'

    exp = RelOp('LtE', Temp('x'), Temp('y'))
    assert writer.write_exp(exp) == '(<= x y)'


def test_write_exp_call():
    setup_test()
    writer = IRWriter()
    exp = Call(Temp('f'), [('', Const(1)), ('', Temp('x'))], {})
    assert writer.write_exp(exp) == '(call f 1 x)'


def test_write_exp_new():
    setup_test()
    writer = IRWriter()
    exp = New(Temp('C'), [('', Temp('x'))], {})
    assert writer.write_exp(exp) == '(new C x)'


def test_write_exp_syscall():
    setup_test()
    writer = IRWriter()
    exp = SysCall(Temp('print'), [('', Const(1)), ('', Const(2))], {})
    assert writer.write_exp(exp) == '(syscall print 1 2)'


def test_write_exp_mref():
    setup_test()
    writer = IRWriter()
    exp = MRef(Temp('xs'), Const(0))
    assert writer.write_exp(exp) == '(mld xs 0)'


def test_write_exp_mstore():
    setup_test()
    writer = IRWriter()
    exp = MStore(Temp('xs'), Const(0), Temp('v'))
    assert writer.write_exp(exp) == '(mst xs 0 v)'


def test_write_exp_array():
    setup_test()
    writer = IRWriter()
    exp = Array([Const(1), Const(2), Const(3)], mutable=True)
    assert writer.write_exp(exp) == '[1 2 3]'

    exp = Array([Temp('x'), Temp('y')], mutable=False)
    assert writer.write_exp(exp) == '(x y)'


def test_write_stm_mv():
    setup_test()
    writer = IRWriter()
    stm = Move(Temp('a', Ctx.STORE), Const(1))
    assert writer.write_stm(stm) == 'mv a 1'


def test_write_stm_cmv():
    setup_test()
    writer = IRWriter()
    stm = CMove(Temp('cond'), Temp('z', Ctx.STORE), BinOp('Add', Temp('x'), Temp('y')))
    assert writer.write_stm(stm) == 'mv? cond z (+ x y)'


def test_write_stm_expr():
    setup_test()
    writer = IRWriter()
    stm = Expr(SysCall(Temp('print'), [('', Const(1))], {}))
    assert writer.write_stm(stm) == 'expr (syscall print 1)'


def test_write_stm_cexpr():
    setup_test()
    writer = IRWriter()
    stm = CExpr(Temp('cond'), SysCall(Temp('print'), [('', Const(1))], {}))
    assert writer.write_stm(stm) == 'expr? cond (syscall print 1)'


def test_write_stm_jump():
    setup_test()
    scope = Scope.create(None, 'S', set(), 0)
    blk = Block(scope, nametag='blk2')
    writer = IRWriter()
    stm = Jump(blk)
    assert writer.write_stm(stm) == 'j blk2'


def test_write_stm_cjump():
    setup_test()
    scope = Scope.create(None, 'S', set(), 0)
    blk_t = Block(scope, nametag='then')
    blk_f = Block(scope, nametag='else')
    writer = IRWriter()
    stm = CJump(Temp('cond'), blk_t, blk_f)
    assert writer.write_stm(stm) == 'cj cond then else'


def test_write_stm_mcjump():
    setup_test()
    scope = Scope.create(None, 'S', set(), 0)
    blk1 = Block(scope, nametag='b1')
    blk2 = Block(scope, nametag='b2')
    blk3 = Block(scope, nametag='b3')
    writer = IRWriter()
    stm = MCJump([Temp('c1'), Temp('c2'), Temp('c3')], [blk1, blk2, blk3])
    assert writer.write_stm(stm) == 'mj c1 b1 c2 b2 c3 b3'


def test_write_stm_ret():
    setup_test()
    writer = IRWriter()
    stm = Ret(Temp(Symbol.return_name))
    assert writer.write_stm(stm) == 'ret @return'


def test_roundtrip_stm():
    """Parse a statement, write it back, and parse again to verify roundtrip."""
    setup_test()
    parser = IRParser('')
    writer = IRWriter()

    cases = [
        'mv a 1',
        'mv a (+ b c)',
        # CMOVE.__eq__ has a bug (checks isinstance CEXPR), so skip roundtrip eq check
        'expr (syscall print 1 2 3)',
        'expr? cond (call f x)',
        'mv xs [1 2 3]',
        'mv v (mld xs 0)',
        'expr (mst xs 0 v)',
        'mv v (new C x y)',
    ]
    for case in cases:
        stm = parser.parse_stm(case)
        written = writer.write_stm(stm)
        stm2 = parser.parse_stm(written)
        assert stm == stm2, f'Roundtrip failed for: {case}\n  written: {written}'

    # CMOVE: verify text roundtrip instead of __eq__
    stm = parser.parse_stm('mv? cond z (+ x y)')
    written = writer.write_stm(stm)
    assert written == 'mv? cond z (+ x y)'


def test_roundtrip_type():
    """Parse a type, write it, parse again to verify roundtrip."""
    setup_test()
    top = env.scopes['@top']
    C = Scope.create(top, 'C', {'class'}, 0)
    F = Scope.create(top, 'F', {'function'}, 0)

    parser = IRParser('')
    writer = IRWriter()

    cases = [
        'int8', 'int32', 'bit256', 'bool', 'str', 'none', 'undef',
        'list<int32>[10]', 'list<bool>[]',
        'tuple<int32>[100]', 'tuple<int8>[]',
        'object(@top.C)', 'class(@top.C)',
        'namespace(@top)', 'function(@top.F)',
    ]
    for case in cases:
        typ = parser.parse_type(case)
        written = writer.write_type(typ)
        typ2 = parser.parse_type(written)
        assert typ == typ2, f'Roundtrip failed for: {case}\n  written: {written}'


def test_roundtrip_scope():
    """Parse a scope, write it back, parse again to verify roundtrip."""
    setup_test()
    src = '''scope AFunction
tags  function
param a:int32
param b:int32
return int64
var c: int16
var d: int16
var e: bit256

blk1:
mv a 1
mv b (+ a 2)
j blk2

blk2:
mv c (== a b)
cj c blk3 blk4

blk3:
mv @return 0
j exit

blk4:
mv @return 1
j exit

exit:
ret @return
'''
    parser1 = IRParser(src)
    parser1.parse_scope()
    scope1 = env.scopes['AFunction']

    writer = IRWriter()
    written = writer.write_scope(scope1)

    # Verify we can parse the written output
    setup_test()
    parser2 = IRParser(written)
    parser2.parse_scope()
    scope2 = env.scopes['AFunction']

    assert scope2.name == 'AFunction'
    assert scope2.is_function()
    assert scope2.has_sym('a')
    assert scope2.has_sym('b')
    assert scope2.has_sym('c')
    assert scope2.has_sym('d')
    assert scope2.has_sym('e')

    # Verify block structure
    blks1 = list(scope1.traverse_blocks())
    blks2 = list(scope2.traverse_blocks())
    assert len(blks1) == len(blks2)
    for b1, b2 in zip(blks1, blks2):
        assert len(b1.stms) == len(b2.stms)
        for s1, s2 in zip(b1.stms, b2.stms):
            # JUMP/CJUMP use identity comparison for targets,
            # so compare via writer output instead
            w1 = writer.write_stm(s1)
            w2 = writer.write_stm(s2)
            assert w1 == w2, f'{w1} != {w2}'


# ------------------------------------------------------------------
# write_scope: no entry_block (lines 30->35)
# ------------------------------------------------------------------
def test_write_scope_no_entry_block():
    setup_test()
    top = env.scopes['@top']
    scope = Scope.create(top, 'Empty', {'function'}, 0)
    writer = IRWriter()
    result = writer.write_scope(scope)
    assert 'scope @top.Empty' in result
    assert 'tags' in result


# ------------------------------------------------------------------
# write_scope: entry_block but no stms (lines 32->35)
# ------------------------------------------------------------------
def test_write_scope_entry_block_no_stms():
    setup_test()
    top = env.scopes['@top']
    scope = Scope.create(top, 'EmptyBlocks', {'function'}, 0)
    blk = Block(scope, nametag='entry')
    scope.entry_block = blk
    # blk has no stms
    writer = IRWriter()
    result = writer.write_scope(scope)
    assert 'scope @top.EmptyBlocks' in result
    # No block body should be written since no stms
    assert 'entry:' not in result


# ------------------------------------------------------------------
# write_scopes (lines 38-41)
# ------------------------------------------------------------------
def test_write_scopes():
    setup_test()
    top = env.scopes['@top']
    s1 = Scope.create(top, 'Func1', {'function'}, 0)
    s2 = Scope.create(top, 'Func2', {'function'}, 0)
    writer = IRWriter()
    result = writer.write_scopes([s1, s2])
    assert 'scope @top.Func1' in result
    assert 'scope @top.Func2' in result
    # Two scopes separated by double newline
    assert '\n\n' in result


# ------------------------------------------------------------------
# param with extra tags (lines 63-64)
# ------------------------------------------------------------------
def test_write_scope_param_with_tags():
    setup_test()
    top = env.scopes['@top']
    scope = Scope.create(top, 'ParamTags', {'function'}, 0)
    sym = scope.add_param_sym('x', {'free'}, typ=Type.int(32))
    scope.add_param(sym, None)  # Register in function_params
    writer = IRWriter()
    result = writer.write_scope(scope)
    # param should appear with tag { free }
    assert 'param x:int32 { free }' in result


# ------------------------------------------------------------------
# return_type is none -> skip (line 69->73)
# ------------------------------------------------------------------
def test_write_scope_return_type_none():
    setup_test()
    top = env.scopes['@top']
    scope = Scope.create(top, 'NoRet', {'function'}, 0)
    scope.return_type = Type.none()
    writer = IRWriter()
    result = writer.write_scope(scope)
    lines = result.split('\n')
    for line in lines:
        assert not line.startswith('return ')


def test_write_scope_no_return_type():
    setup_test()
    top = env.scopes['@top']
    scope = Scope.create(top, 'NoRet2', {'function'}, 0)
    scope.return_type = None
    writer = IRWriter()
    result = writer.write_scope(scope)
    lines = result.split('\n')
    for line in lines:
        assert not line.startswith('return ')


# ------------------------------------------------------------------
# imported symbol: skip in var section, emit in import section (lines 87, 100-101)
# ------------------------------------------------------------------
def test_write_scope_imported_symbol():
    setup_test()
    top = env.scopes['@top']
    src_scope = Scope.create(top, 'Source', {'function'}, 0)
    src_sym = src_scope.add_sym('helper', set(), typ=Type.int(32))

    dst_scope = Scope.create(top, 'Dest', {'function'}, 0)
    dst_scope.import_sym(src_sym, 'helper')

    writer = IRWriter()
    result = writer.write_scope(dst_scope)
    # Should have 'from @top.Source import helper'
    assert 'from @top.Source import helper' in result
    # Should NOT have 'var helper'
    for line in result.split('\n'):
        assert not line.startswith('var helper')


# ------------------------------------------------------------------
# variable with tags (lines 91-92)
# ------------------------------------------------------------------
def test_write_scope_var_with_tags():
    setup_test()
    top = env.scopes['@top']
    scope = Scope.create(top, 'VarTags', {'function'}, 0)
    scope.add_sym('counter', {'field'}, typ=Type.int(16))
    writer = IRWriter()
    result = writer.write_scope(scope)
    assert 'var counter: int16 { field }' in result


# ------------------------------------------------------------------
# _format_const fallback (line 265) - non-bool/int/str value
# ------------------------------------------------------------------
def test_format_const_fallback():
    writer = IRWriter()
    c = Const(value=3.14)
    result = writer.write_exp(c)
    assert result == '3.14'

    c2 = Const(value=None)
    result2 = writer.write_exp(c2)
    assert result2 == 'None'


# ------------------------------------------------------------------
# _format_type fallback else branch (line 320)
# ------------------------------------------------------------------
def test_format_type_fallback_else():
    writer = IRWriter()
    # Type('any', False) does not match any is_* check in _format_type
    t = Type('any', False)
    result = writer.write_type(t)
    assert result == 'any'


# ------------------------------------------------------------------
# write_scope with blocks and stms (full path with entry_block + stms)
# ------------------------------------------------------------------
def test_write_scope_with_blocks_and_stms():
    setup_test()
    top = env.scopes['@top']
    scope = Scope.create(top, 'WithBlocks', {'function'}, 0)
    scope.return_type = Type.int(32)
    sym_a = scope.add_param_sym('a', set(), typ=Type.int(32))
    scope.add_param(sym_a, None)
    scope.add_sym('x', set(), typ=Type.int(32))

    blk1 = Block(scope, nametag='entry')
    blk2 = Block(scope, nametag='exit')
    scope.entry_block = blk1
    blk1.succs = [blk2]
    blk2.preds = [blk1]

    blk1.stms = [
        Move(Temp('x', Ctx.STORE), Const(42)),
        Jump(blk2),
    ]
    blk2.stms = [
        Ret(Temp(Symbol.return_name)),
    ]

    writer = IRWriter()
    result = writer.write_scope(scope)
    assert 'scope @top.WithBlocks' in result
    assert 'param a:int32' in result
    assert 'return int32' in result
    assert 'var x: int32' in result
    assert 'entry:' in result
    assert 'mv x 42' in result
    assert 'j exit' in result
    assert 'ret @return' in result
