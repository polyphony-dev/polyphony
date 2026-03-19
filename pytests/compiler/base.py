"""Test utilities for compiler unit tests."""
import os
from polyphony.compiler.common.env import env
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.builtin import builtin_symbols, clear_builtins


# ============================================================
# Lightweight mocks for IR unit tests
# ============================================================

class MockScope:
    """Minimal scope-like object for Block construction without full env setup."""
    def __init__(self, name='test'):
        self.name = name
        self.block_count = 0
        self.block_map = {}


def make_block(scope=None, nametag='b'):
    """Create a Block with a lightweight mock scope."""
    if scope is None:
        scope = MockScope()
    return Block(scope, nametag)


def setup_test(with_global=True):
    """Initialize env and symbol state for a test.

    Mirrors __main__.initialize() + setup_builtins() + setup_global().
    """
    from polyphony.compiler.__main__ import initialize, setup_builtins, setup_global
    initialize()
    setup_builtins()
    if with_global:
        setup_global('dummy')


def setup_libs(*modules):
    """Translate polyphony library modules from actual source files.

    Call after setup_test(). Translates the real _internal/*.py files
    so tests get authentic library scopes instead of hand-written IR fragments.

    Args:
        *modules: Module names to load. Supported: 'io', 'timing', 'typing', 'modules'.
                  If empty, loads 'io' and 'timing' by default.
    """
    from polyphony.compiler.frontend.python.irtranslator import ImportVisitor
    from polyphony.compiler.ir.types.type import Type

    if not modules:
        modules = ('io', 'timing')

    internal_dir = os.path.join(env.root_dir, '_internal')
    iv = ImportVisitor(env.scopes[env.global_scope_name])

    for mod in modules:
        full_name = f'polyphony.{mod}'
        if full_name not in env.scopes:
            iv._find_and_set_hierarchy(full_name)


def install_builtins(scope):
    """Import builtin symbols into the given scope."""
    for asname, sym in builtin_symbols.items():
        scope.import_sym(sym, asname)

