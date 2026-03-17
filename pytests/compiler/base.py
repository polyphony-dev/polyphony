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


def install_builtins(scope):
    """Import builtin symbols into the given scope."""
    for asname, sym in builtin_symbols.items():
        scope.import_sym(sym, asname)


# IR source fragments for builtin library scopes used in tests.
# These provide minimal scope definitions needed by tests that
# reference polyphony library types.
lib_source_polyphony = """
scope polyphony
tags lib namespace
"""

lib_source_polyphony_io = """
scope polyphony.io
tags lib namespace
var Port: class(polyphony.io.Port)
var flipped: function(polyphony.io.flipped)
var connect: function(polyphony.io.connect)
var thru: function(polyphony.io.thru)

scope polyphony.io.Port
tags lib class port
var __init__: function(polyphony.io.Port.__init__)
var rd: function(polyphony.io.Port.rd)
var wr: function(polyphony.io.Port.wr)
var assign: function(polyphony.io.Port.assign)
var edge: function(polyphony.io.Port.edge)

scope polyphony.io.Port.__init__
tags lib function method ctor
param dtype:class()
param direction:str
param init:int32
param rewritable:bool

scope polyphony.io.Port.rd
tags lib function method returnable
return int32

scope polyphony.io.Port.wr
tags lib function method
param v:int32

scope polyphony.io.Port.assign
tags lib function method
param fn:function()

scope polyphony.io.Port.edge
tags lib function method returnable
param old:int32
param new:int32
return bool

scope polyphony.io.flipped
tags lib builtin function
param obj:object()
return object()

scope polyphony.io.connect
tags lib builtin function
param p0:object()
param p1:object()

scope polyphony.io.thru
tags lib builtin function
param parent:object()
param child:object()
"""

lib_source_polyphony_channel = """
scope polyphony.io.Channel
tags lib class module
var __init__: function(polyphony.io.Channel.__init__)
var put: function(polyphony.io.Channel.put)
var get: function(polyphony.io.Channel.get)
var full: function(polyphony.io.Channel.full)
var empty: function(polyphony.io.Channel.empty)

scope polyphony.io.Channel.__init__
tags lib function method ctor
param dtype:class()
param capacity:int32

scope polyphony.io.Channel.put
tags lib function method
param v:int32

scope polyphony.io.Channel.get
tags lib function method returnable
return int32

scope polyphony.io.Channel.full
tags lib function method returnable
return bool

scope polyphony.io.Channel.empty
tags lib function method returnable
return bool
"""

lib_source_polyphony_timing = """
scope polyphony.timing
tags lib namespace
var clksleep: function(polyphony.timing.clksleep)
var wait_value: function(polyphony.timing.wait_value)
var wait_until: function(polyphony.timing.wait_until)

scope polyphony.timing.wait_until
tags lib builtin function
param pred:function()
return bool

scope polyphony.timing.clksleep
tags lib function

scope polyphony.timing.wait_value
tags inlinelib function enclosure
param value:int32 { free }
param port:object(polyphony.io.Port) { free }
return none
var lambda: function(polyphony.timing.wait_value.lambda)

blk1:
mv value @in_value
mv port @in_port
expr (call wait_until lambda)

scope polyphony.timing.wait_value.lambda
tags inlinelib function returnable closure comb
return bool

blk1:
mv @return (== (call port.rd) value)
ret @return
"""


def register_lib_syms():
    """Register child symbols in polyphony namespace after IRParser.

    Call after IRParser().parse_scope() when lib_source fragments are used.
    Registers io/timing namespaces in polyphony scope based on what was parsed.
    """
    from polyphony.compiler.ir.types.type import Type
    polyphony_scope = env.scopes.get('polyphony')
    if not polyphony_scope:
        return
    if 'polyphony.io' in env.scopes and not polyphony_scope.find_sym('io'):
        polyphony_scope.add_sym('io', tags=set(), typ=Type.namespace('polyphony.io'))
    if 'polyphony.timing' in env.scopes and not polyphony_scope.find_sym('timing'):
        polyphony_scope.add_sym('timing', tags=set(), typ=Type.namespace('polyphony.timing'))
    io_scope = env.scopes.get('polyphony.io')
    if io_scope:
        if 'polyphony.io.Channel' in env.scopes and not io_scope.find_sym('Channel'):
            io_scope.add_sym('Channel', tags=set(), typ=Type.klass('polyphony.io.Channel'))
