from polyphony.compiler.common.env import env
from polyphony.compiler.ir.ir import Const
from pytests.compiler.base import setup_test

def test_setup_test():
    setup_test()
    assert env.current_filename == 'dummy'
    assert env.ctor_name == '__init__'
    assert env.callop_name == '__call__'
    assert env.global_scope_name == '@top'
    assert env.self_name == 'self'
    assert env.scopes

    assert '__builtin__' in env.scopes
    assert env.scopes['__builtin__'].tags == {'builtin', 'lib', 'namespace'}

    for tclass in ['none', 'int', 'bool', 'str', 'list', 'tuple', 'function', 'type']:
        assert f'__builtin__.{tclass}' in env.scopes
        assert env.scopes[f'__builtin__.{tclass}'].tags == {'builtin', 'lib', 'class', 'typeclass'}
        assert f'__builtin__.{tclass}.__init__' in env.scopes
    assert f'__builtin__.object' in env.scopes
    assert env.scopes[f'__builtin__.object'].tags == {'builtin', 'lib', 'class', 'typeclass', 'object'}

    for func in ['print', 'range', '_assert', '_new']:
        assert f'__builtin__.{func}' in env.scopes
        assert env.scopes[f'__builtin__.{func}'].tags == {'builtin', 'lib', 'function'}
    for func in ['len']:
        assert f'__builtin__.{func}' in env.scopes
        assert env.scopes[f'__builtin__.{func}'].tags == {'builtin', 'lib', 'function', 'returnable'}

    assert '@top' in env.scopes
    top = env.scopes['@top']
    assert top.tags == {'global', 'namespace'}

    for symname in ['__name__', '__file__', 'none', 'int', 'bool', 'str', 'list', 'tuple', 'object', 'function', 'type', 'print', 'range', 'len', 'assert', '$new']:
        assert symname in top.symbols

    # const strings
    name = top.symbols['__name__']
    assert name.typ.is_str()
    assert isinstance(top.constants[name], Const)
    assert top.constants[name].value == '__main__'
    file = top.symbols['__file__']
    assert file.typ.is_str()
    assert isinstance(top.constants[file], Const)
    assert top.constants[file].value == 'dummy'

    # type class symbols
    for tclass in ['none', 'int', 'bool', 'str', 'list', 'tuple', 'object', 'function', 'type']:
        sym = top.symbols[tclass]
        assert sym.typ.is_class()
        assert sym.typ.scope is env.scopes[f'__builtin__.{tclass}']
    # functions
    _print = top.symbols['print']
    assert _print.typ.is_function()
    assert _print.typ.scope is env.scopes['__builtin__.print']
    _range = top.symbols['range']
    assert _range.typ.is_function()
    assert _range.typ.scope is env.scopes['__builtin__.range']
    _len = top.symbols['len']
    assert _len.typ.is_function()
    assert _len.typ.scope is env.scopes['__builtin__.len']
    _assert = top.symbols['assert']
    assert _assert.typ.is_function()
    assert _assert.typ.scope is env.scopes['__builtin__._assert']
    _new = top.symbols['$new']
    assert _new.typ.is_function()
    assert _new.typ.scope is env.scopes['__builtin__._new']
