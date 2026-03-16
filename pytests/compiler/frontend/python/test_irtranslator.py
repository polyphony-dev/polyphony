import types
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir import ir as new
from polyphony.compiler.ir.ir_helper import irexp_type
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.frontend.python.irtranslator import IRTranslator
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def test_parse_expr():
    setup_test()
    src = '''
from polyphony.typing import List
List[0][1]
'''
    IRTranslator().translate(src, '')
    assert env.global_scope_name in env.scopes
    top = env.scopes[env.global_scope_name]
    stm = top.entry_block.stms[0]
    assert isinstance(stm, Expr)
    assert isinstance(stm.exp, MRef)
    mref = stm.exp
    assert isinstance(mref.mem, MRef)
    assert isinstance(mref.offset, Const)
    assert mref.offset.value == 1
    mref = mref.mem

    list_var = mref.mem
    assert isinstance(list_var, Temp)
    assert list_var.name == 'List'
    list_t = irexp_type(list_var, top)
    assert list_t.is_class()
    list_class = list_t.scope
    assert list_class.is_typeclass()

    assert isinstance(mref.offset, Const)
    assert mref.offset.value == 0

def test_parse_function_params():
    setup_test()
    src = '''
def f(a, b=10, c=20):
    pass
'''
    IRTranslator().translate(src, '')
    scope = env.scopes['@top.f']

    syms = scope.param_symbols()
    assert len(syms) == 3
    assert syms[0].name == '@in_a'
    assert syms[1].name == '@in_b'
    assert syms[2].name == '@in_c'

    vals = scope.param_default_values()
    assert len(vals) == 3
    assert vals[0] == None
    assert isinstance(vals[1], Const) and vals[1].value == 10
    assert isinstance(vals[2], Const) and vals[2].value == 20

def test_parse_class_params():
    setup_test()
    src = '''
class C:
    def __init__(self, a, b=123):
        self.a = a
        self.b = b
'''
    IRTranslator().translate(src, '')
    scope = env.scopes['@top.C.__init__']
    syms = scope.param_symbols(with_self=True)
    assert len(syms) == 3
    assert syms[0].name == '@in_self'
    assert syms[1].name == '@in_a'
    assert syms[2].name == '@in_b'
    syms = scope.param_symbols(with_self=False)
    assert len(syms) == 2
    assert syms[0].name == '@in_a'
    assert syms[1].name == '@in_b'

    vals = scope.param_default_values()
    assert len(vals) == 2
    assert vals[0] == None
    assert isinstance(vals[1], Const) and vals[1].value == 123

def test_parse_class_noparams():
    setup_test()
    src = '''
class D:
    pass
'''
    IRTranslator().translate(src, '')
    D = env.scopes['@top.D']
    ctor = env.scopes['@top.D.__init__']
    ctor_sym = D.find_sym('__init__')
    assert ctor_sym
    assert ctor_sym.typ.is_function()
    assert ctor_sym.typ.scope is ctor

    syms = ctor.param_symbols(with_self=True)
    assert len(syms) == 1
    assert syms[0].name == '@in_self'
    assert syms[0].is_self()

