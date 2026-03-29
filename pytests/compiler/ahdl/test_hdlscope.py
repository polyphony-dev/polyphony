"""Tests covering uncovered lines in polyphony/compiler/ahdl/hdlscope.py."""
import pytest
from collections import defaultdict

from polyphony.compiler.ahdl.hdlscope import HDLScope
from polyphony.compiler.ahdl.hdlmodule import HDLModule
from polyphony.compiler.ahdl.signal import Signal
from polyphony.compiler.ir.irreader import IrReader
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


_SRC = '''
scope test
tags function returnable
'''


def build_scope():
    setup_test()
    parser = IrReader(_SRC)
    parser.parse_scope()
    for name in parser.sources:
        return env.scopes[name]


def make_hdlmodule():
    scope = build_scope()
    hdl = HDLModule(scope, scope.base_name, scope.base_name)
    env.append_hdlscope(hdl)
    return hdl


# ============================================================
# __str__ and str_signals — lines 19-35
# ============================================================

def test_str_basic():
    hdl = make_hdlmodule()
    s = str(hdl)
    assert 'HDLModule' in s or 'test' in s


def test_str_signals_no_signals():
    hdl = make_hdlmodule()
    # HDLScope.str_signals is called from HDLModule.__str__; test via HDLScope directly
    scope = hdl.scope
    hs = HDLScope(scope, 'child', 'child')
    s = hs.str_signals()
    assert '-- signals --' in s


def test_str_signals_with_plain_signal():
    hdl = make_hdlmodule()
    hdl.gen_sig('reg_a', 8, {'reg'})
    s = hdl.str_signals()
    assert 'reg_a' in s


def test_str_dunder_includes_name_and_signals():
    scope = build_scope()
    hs = HDLScope(scope, 'myhdlscope', 'myhdlscope')
    hs.gen_sig('sigx', 4, {'reg'})
    s = str(hs)
    assert 'myhdlscope' in s
    assert 'sigx' in s


def test_str_signals_with_subscope_signal():
    """str_signals walks into subscopes for signals tagged 'subscope'."""
    scope = build_scope()
    parent_hs = HDLScope(scope, 'parent', 'parent')
    child_hs = HDLScope(scope, 'child', 'child')
    child_hs.gen_sig('child_reg', 4, {'reg'})

    # Create a signal with 'subscope' tag and attach the child scope
    sub_sig = parent_hs.gen_sig('sub_inst', 8, {'subscope'})
    parent_hs.add_subscope(sub_sig, child_hs)

    s = parent_hs.str_signals()
    assert 'sub_inst' in s
    assert 'child_reg' in s


# ============================================================
# clone() and clone_core() — lines 37-56
# ============================================================

def test_clone_basic():
    hdl = make_hdlmodule()
    hdl.gen_sig('orig_sig', 8, {'reg'})
    scope = hdl.scope
    hs = HDLScope(scope, 'original', 'original')
    hs.gen_sig('s1', 4, {'reg'})
    hs.gen_sig('s2', 8, {'net'})
    clone = hs.clone()
    assert 's1' in clone.signals
    assert 's2' in clone.signals
    assert clone.name == 'original'


def test_clone_signals_are_independent():
    scope = build_scope()
    hs = HDLScope(scope, 'hs', 'hs')
    orig_sig = hs.gen_sig('mysig', 16, {'reg'})
    clone = hs.clone()
    # Modifying the clone's signal width should not affect original
    clone.signals['mysig'].width = 999
    assert orig_sig.width == 16


def test_clone_with_sym():
    """clone_core populates sig2sym when sym is not None."""
    from polyphony.compiler.ir.irreader import IrReader
    setup_test()
    src = '''
scope clonetest
tags function returnable
var v: int32

blk1:
ret @return
'''
    parser = IrReader(src)
    parser.parse_scope()
    scope = None
    for name in parser.sources:
        scope = env.scopes[name]
    assert scope is not None
    hdl = HDLModule(scope, scope.base_name, scope.base_name)
    env.append_hdlscope(hdl)
    sym = list(scope.symbols.values())[0]
    hdl.gen_sig('sym_sig', 8, {'reg'}, sym)
    clone = hdl.clone()
    assert 'sym_sig' in clone.signals


def test_clone_with_subscope():
    """clone_core recursively clones subscopes."""
    scope = build_scope()
    parent = HDLScope(scope, 'parent', 'parent')
    child = HDLScope(scope, 'child', 'child')
    child.gen_sig('child_sig', 4, {'reg'})
    sub_sig = parent.gen_sig('sub_inst', 8, {'subscope'})
    parent.add_subscope(sub_sig, child)

    cloned = parent.clone()
    assert 'sub_inst' in cloned.signals
    cloned_sub_sig = cloned.signals['sub_inst']
    assert cloned_sub_sig in cloned.subscopes
    cloned_child = cloned.subscopes[cloned_sub_sig]
    assert 'child_sig' in cloned_child.signals


# ============================================================
# gen_sig() — lines 58-71
# ============================================================

def test_gen_sig_creates_new_signal():
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('newsig', 8, {'reg'})
    assert sig.name == 'newsig'
    assert sig.width == 8
    assert 'reg' in sig.tags


def test_gen_sig_updates_existing_width():
    hdl = make_hdlmodule()
    hdl.gen_sig('dup', 8, {'reg'})
    sig2 = hdl.gen_sig('dup', 16)
    assert sig2.width == 16


def test_gen_sig_updates_existing_adds_tag():
    hdl = make_hdlmodule()
    hdl.gen_sig('tagged', 8, {'reg'})
    sig2 = hdl.gen_sig('tagged', 8, {'net'})
    assert 'net' in sig2.tags


def test_gen_sig_with_sym_populates_sym2sigs():
    setup_test()
    src = '''
scope sym_test
tags function returnable
var v: int32

blk1:
ret @return
'''
    parser = IrReader(src)
    parser.parse_scope()
    scope = None
    for name in parser.sources:
        scope = env.scopes[name]
    assert scope is not None
    hdl = HDLModule(scope, scope.base_name, scope.base_name)
    env.append_hdlscope(hdl)
    sym = list(scope.symbols.values())[0]
    sig = hdl.gen_sig('sym_sig2', 8, {'reg'}, sym)
    assert sym in hdl.sym2sigs
    assert sig in hdl.sym2sigs[sym]
    assert hdl.sig2sym[sig] == sym


def test_gen_sig_no_tag():
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('notag', 4)
    assert sig.name == 'notag'


# ============================================================
# signal() lookup — lines 73-85
# ============================================================

def test_signal_by_str_found():
    hdl = make_hdlmodule()
    hdl.gen_sig('lookup_me', 8, {'reg'})
    result = hdl.signal('lookup_me')
    assert result is not None
    assert result.name == 'lookup_me'


def test_signal_by_str_not_found_returns_none():
    hdl = make_hdlmodule()
    result = hdl.signal('nonexistent')
    assert result is None


def test_signal_by_symbol_found_single():
    """symbol() returns the signal when exactly one sig maps to a sym."""
    setup_test()
    src = '''
scope sym_lookup
tags function returnable
var v: int32

blk1:
ret @return
'''
    parser = IrReader(src)
    parser.parse_scope()
    scope = None
    for name in parser.sources:
        scope = env.scopes[name]
    assert scope is not None
    hdl = HDLModule(scope, scope.base_name, scope.base_name)
    env.append_hdlscope(hdl)
    sym = list(scope.symbols.values())[0]
    sig = hdl.gen_sig('sym_lookup_sig', 8, {'reg'}, sym)
    result = hdl.signal(sym)
    assert result is sig


def test_signal_by_symbol_not_found_returns_none():
    """symbol() for a Symbol not in sym2sigs returns None (no bases)."""
    from polyphony.compiler.ir.types.type import Type
    hdl = make_hdlmodule()
    # Create a fresh symbol not associated with any signal
    scope = hdl.scope
    sym = scope.add_sym('fresh_sym', set(), Type.int(32))
    result = hdl.signal(sym)
    assert result is None


def test_signal_by_symbol_multiple_sigs_returns_none():
    """symbol() with more than one sig for a sym returns None."""
    setup_test()
    src = '''
scope multi_sym
tags function returnable
var v: int32

blk1:
ret @return
'''
    parser = IrReader(src)
    parser.parse_scope()
    scope = None
    for name in parser.sources:
        scope = env.scopes[name]
    assert scope is not None
    hdl = HDLModule(scope, scope.base_name, scope.base_name)
    env.append_hdlscope(hdl)
    sym = list(scope.symbols.values())[0]
    # Register two different signals for the same sym manually
    sig1 = Signal(hdl, 'multi_sig1', 8, {'reg'}, sym)
    sig2 = Signal(hdl, 'multi_sig2', 8, {'reg'}, sym)
    hdl.signals['multi_sig1'] = sig1
    hdl.signals['multi_sig2'] = sig2
    hdl.sym2sigs[sym].append(sig1)
    hdl.sym2sigs[sym].append(sig2)
    result = hdl.signal(sym)
    assert result is None


# ============================================================
# get_signals() — lines 87-106
# ============================================================

def test_get_signals_all():
    hdl = make_hdlmodule()
    hdl.gen_sig('ga', 8, {'reg'})
    hdl.gen_sig('gb', 8, {'net'})
    sigs = hdl.get_signals()
    names = [s.name for s in sigs]
    assert 'ga' in names
    assert 'gb' in names


def test_get_signals_include_tags():
    hdl = make_hdlmodule()
    hdl.gen_sig('inc_reg', 8, {'reg'})
    hdl.gen_sig('inc_net', 8, {'net'})
    sigs = hdl.get_signals(include_tags={'reg'})
    names = [s.name for s in sigs]
    assert 'inc_reg' in names
    assert 'inc_net' not in names


def test_get_signals_exclude_tags():
    hdl = make_hdlmodule()
    hdl.gen_sig('exc_reg', 8, {'reg'})
    hdl.gen_sig('exc_net', 8, {'net'})
    sigs = hdl.get_signals(exclude_tags={'net'})
    names = [s.name for s in sigs]
    assert 'exc_reg' in names
    assert 'exc_net' not in names


def test_get_signals_include_requires_set():
    hdl = make_hdlmodule()
    hdl.gen_sig('chk', 4, {'reg'})
    with pytest.raises(AssertionError):
        hdl.get_signals(include_tags=['reg'])  # list not allowed


def test_get_signals_exclude_requires_set():
    hdl = make_hdlmodule()
    hdl.gen_sig('chk2', 4, {'reg'})
    with pytest.raises(AssertionError):
        hdl.get_signals(exclude_tags=['reg'])  # list not allowed


def test_get_signals_sorted_by_name():
    hdl = make_hdlmodule()
    hdl.gen_sig('zzz', 4, {'reg'})
    hdl.gen_sig('aaa', 4, {'reg'})
    hdl.gen_sig('mmm', 4, {'reg'})
    sigs = hdl.get_signals()
    names = [s.name for s in sigs]
    sorted_names = sorted(names)
    assert names == sorted_names


def test_get_signals_with_base_false():
    """with_base=False (default) does not iterate scope.bases."""
    hdl = make_hdlmodule()
    hdl.gen_sig('local_sig', 8, {'reg'})
    sigs = hdl.get_signals(with_base=False)
    names = [s.name for s in sigs]
    assert 'local_sig' in names


# ============================================================
# remove_sig() — lines 108-114
# ============================================================

def test_remove_sig_by_name():
    hdl = make_hdlmodule()
    hdl.gen_sig('to_remove', 8, {'reg'})
    hdl.remove_sig('to_remove')
    assert 'to_remove' not in hdl.signals


def test_remove_sig_by_signal_object():
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('obj_remove', 8, {'reg'})
    hdl.remove_sig(sig)
    assert 'obj_remove' not in hdl.signals


def test_remove_sig_nonexistent_str_raises():
    hdl = make_hdlmodule()
    with pytest.raises(AssertionError):
        hdl.remove_sig('ghost')


def test_remove_sig_nonexistent_signal_raises():
    """Removing a Signal whose name is not in signals raises AssertionError."""
    hdl = make_hdlmodule()
    scope = hdl.scope
    fake_sig = Signal(hdl, 'ghost_obj', 8, {'reg'})
    with pytest.raises(AssertionError):
        hdl.remove_sig(fake_sig)


# ============================================================
# add_subscope() — line 116-117
# ============================================================

def test_add_subscope():
    scope = build_scope()
    parent = HDLScope(scope, 'par', 'par')
    child = HDLScope(scope, 'ch', 'ch')
    sub_sig = parent.gen_sig('child_inst', 8, {'subscope'})
    parent.add_subscope(sub_sig, child)
    assert parent.subscopes[sub_sig] is child
