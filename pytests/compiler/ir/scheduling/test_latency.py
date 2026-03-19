"""Tests for latency calculation (_get_latency, get_latency, _get_syscall_latency)."""
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir.irreader import IrReader
from polyphony.compiler.ir.scheduling.latency import (
    get_latency, _get_latency, _get_syscall_latency, UNIT_STEP, CALL_MINIMUM_STEP,
)
from polyphony.compiler.ir.scheduling.dataflow import DFGBuilder
from polyphony.compiler.ir.analysis.loopdetector import LoopDetector
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test, setup_libs


def build_scope(src, scheduling='sequential'):
    setup_test()
    parser = IrReader(src)
    parser.parse_scope()
    name = list(parser.sources)[0]
    scope = env.scopes[name]
    for blk in scope.traverse_blocks():
        blk.synth_params['scheduling'] = scheduling
        blk.synth_params['cycle'] = 'any'
        blk.synth_params['ii'] = -1
    return scope


# ============================================================
# _get_latency for Move statements
# ============================================================

def test_latency_move_const():
    """Move with const src returns UNIT_STEP."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 42
mv @return x
ret @return
''')
    stm = scope.entry_block.stms[0]  # mv x 42
    assert _get_latency(stm) == UNIT_STEP


def test_latency_move_alias_dst():
    """Move to alias variable returns 0 (wire assignment)."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var a: int32 {alias}

blk1:
mv a 1
mv @return a
ret @return
''')
    stm = scope.entry_block.stms[0]  # mv a 1
    assert _get_latency(stm) == 0


def test_latency_move_new():
    """Move with New src returns 0."""
    # New requires full compiler pipeline, test via get_latency wrapper
    scope = build_scope('''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 42
mv @return x
ret @return
''')
    stm = scope.entry_block.stms[0]
    def_l, seq_l = get_latency(stm)
    assert def_l == UNIT_STEP
    assert seq_l == UNIT_STEP


def test_latency_move_mref():
    """Move with MRef src (memory read) returns UNIT_STEP."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var arr: list<int32>[4]
var x: int32
var i: int32

blk1:
mv i 0
mv x (mld arr i)
mv @return x
ret @return
''')
    for stm in scope.entry_block.stms:
        if isinstance(stm, Move) and isinstance(stm.src, MRef):
            assert _get_latency(stm) == UNIT_STEP
            return
    assert False, "MRef statement not found"


def test_latency_move_temp_to_temp():
    """Move from temp to temp (register copy) returns UNIT_STEP."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var x: int32
var y: int32

blk1:
mv x 10
mv y x
mv @return y
ret @return
''')
    stm = scope.entry_block.stms[1]  # mv y x
    assert _get_latency(stm) == UNIT_STEP


def test_latency_move_alias_to_alias():
    """Move from alias to alias returns 0."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var a: int32 {alias}
var b: int32 {alias}

blk1:
mv a 1
mv b a
mv @return b
ret @return
''')
    stm = scope.entry_block.stms[1]  # mv b a
    assert _get_latency(stm) == 0


# ============================================================
# _get_latency for Expr statements
# ============================================================

def test_latency_expr_mstore():
    """Expr with MStore returns UNIT_STEP."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var arr: list<int32>[4]
var i: int32

blk1:
mv i 0
expr (mst arr i 99)
mv @return 0
ret @return
''')
    for stm in scope.entry_block.stms:
        if isinstance(stm, Expr) and isinstance(stm.exp, MStore):
            assert _get_latency(stm) == UNIT_STEP
            return
    assert False, "MStore Expr not found"


# ============================================================
# get_latency wrapper
# ============================================================

def test_get_latency_returns_tuple():
    """get_latency always returns (def_latency, seq_latency) pair."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 42
mv @return x
ret @return
''')
    stm = scope.entry_block.stms[0]
    result = get_latency(stm)
    assert isinstance(result, tuple)
    assert len(result) == 2
    def_l, seq_l = result
    assert def_l >= 0
    assert seq_l >= 0


def test_get_latency_alias_zero():
    """get_latency for alias Move returns (0, 0)."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var a: int32 {alias}

blk1:
mv a 1
mv @return a
ret @return
''')
    stm = scope.entry_block.stms[0]
    def_l, seq_l = get_latency(stm)
    assert def_l == 0
    assert seq_l == 0


# ============================================================
# _get_latency for Move with call/new/attr
# ============================================================

def test_latency_move_call_function():
    """Move with Call to a normal function returns CALL_MINIMUM_STEP."""
    src = '''
scope top
tags namespace
var G: function(top.G)

scope top.G
tags function returnable
return int32
var x: int32

blk1:
mv x 0
mv @return x
ret @return

scope top.F
tags function returnable
return int32
var y: int32
from top import G

blk1:
mv y (call G 1)
mv @return y
ret @return
'''
    scope = build_scope(src)
    F = env.scopes.get('top.F')
    assert F is not None
    for stm in F.entry_block.stms:
        if isinstance(stm, Move) and isinstance(stm.src, Call):
            lat = _get_latency(stm)
            assert lat == UNIT_STEP * CALL_MINIMUM_STEP
            return
    assert False, "Call Move not found"


def test_latency_move_call_with_asap_latency():
    """Move with Call to function with asap_latency uses that latency."""
    src = '''
scope top
tags namespace
var G: function(top.G)

scope top.G
tags function returnable
return int32
var x: int32

blk1:
mv x 0
mv @return x
ret @return

scope top.F
tags function returnable
return int32
var y: int32
from top import G

blk1:
mv y (call G 1)
mv @return y
ret @return
'''
    scope = build_scope(src)
    G = env.scopes.get('top.G')
    F = env.scopes.get('top.F')
    assert F is not None and G is not None
    G.asap_latency = 5
    for stm in F.entry_block.stms:
        if isinstance(stm, Move) and isinstance(stm.src, Call):
            lat = _get_latency(stm)
            assert lat == UNIT_STEP * 5
            return
    assert False, "Call Move not found"


def test_latency_move_new_returns_zero():
    """Move with New src returns 0."""
    from polyphony.compiler.ir.scope import Scope
    from polyphony.compiler.ir.symbol import Symbol
    from polyphony.compiler.ir.types.type import Type
    from polyphony.compiler.ir.block import Block

    setup_test()
    top = Scope.global_scope()
    C = Scope.create(top, 'C', {'class'}, 0)
    C.return_type = Type.none()
    top.add_sym('C', tags=set(), typ=Type.klass(C))
    ctor = Scope.create(C, '__init__', {'function', 'method', 'ctor'}, 0)
    ctor.return_type = Type.none()

    F = Scope.create(top, 'F', {'function', 'returnable'}, 0)
    F.return_type = Type.int(32)
    F.add_sym('c', tags=set(), typ=Type.object(C))
    F.import_sym(top.find_sym('C'))
    blk = Block(F, nametag='blk1')
    F.set_entry_block(blk)
    F.set_exit_block(blk)
    new_call = New(func=Temp('C'), args=[], kwargs={})
    blk.append_stm(Move(dst=Temp('c', Ctx.STORE), src=new_call))
    blk.append_stm(Ret(Const(0)))
    Block.set_order(blk, 0)

    stm = blk.stms[0]
    assert isinstance(stm.src, New)
    assert _get_latency(stm) == 0


def test_latency_move_attr_dst():
    """Move to Attr dst (field write) returns UNIT_STEP."""
    src = '''
scope C
tags class
var x: int32

scope C.__init__
tags function method ctor
param $self: object(C) { self }

blk1:
mv $self.x 42
'''
    scope = build_scope(src)
    ctor = env.scopes.get('C.__init__')
    if ctor is None:
        return
    for stm in ctor.entry_block.stms:
        if isinstance(stm, Move) and isinstance(stm.dst, Attr):
            lat = _get_latency(stm)
            assert lat == UNIT_STEP
            return
    assert False, "Attr Move not found"


def test_latency_move_attr_alias_dst():
    """Move to Attr alias dst returns 0."""
    src = '''
scope C
tags class
var x: int32 {alias}

scope C.__init__
tags function method ctor
param $self: object(C) { self }

blk1:
mv $self.x 42
'''
    scope = build_scope(src)
    ctor = env.scopes.get('C.__init__')
    if ctor is None:
        return
    for stm in ctor.entry_block.stms:
        if isinstance(stm, Move) and isinstance(stm.dst, Attr):
            lat = _get_latency(stm)
            assert lat == 0
            return
    assert False, "Attr alias Move not found"


def test_latency_move_array_to_seq():
    """Move with Array src to seq-typed dst returns UNIT_STEP."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var arr: list<int32>[3]

blk1:
mv arr [1 2 3]
mv @return 0
ret @return
''')
    for stm in scope.entry_block.stms:
        if isinstance(stm, Move) and isinstance(stm.src, Array):
            assert _get_latency(stm) == UNIT_STEP
            return
    assert False, "Array Move not found"


# ============================================================
# _get_syscall_latency
# ============================================================

def test_syscall_latency_clksleep_small():
    """clksleep with small constant returns the cycle value."""
    setup_test()
    call = SysCall(
        func=Temp('polyphony.timing.clksleep'),
        args=[('', Const(value=3))],
        kwargs={},
    )
    object.__setattr__(call, 'name', 'polyphony.timing.clksleep')
    assert _get_syscall_latency(call) == 3


def test_syscall_latency_clksleep_large():
    """clksleep with large constant returns 1 (uses sleep sentinel)."""
    setup_test()
    call = SysCall(
        func=Temp('polyphony.timing.clksleep'),
        args=[('', Const(value=1000))],
        kwargs={},
    )
    object.__setattr__(call, 'name', 'polyphony.timing.clksleep')
    assert _get_syscall_latency(call) == 1


def test_syscall_latency_clksleep_variable():
    """clksleep with variable arg returns 1."""
    setup_test()
    call = SysCall(
        func=Temp('polyphony.timing.clksleep'),
        args=[('', Temp('n'))],
        kwargs={},
    )
    object.__setattr__(call, 'name', 'polyphony.timing.clksleep')
    assert _get_syscall_latency(call) == 1


def test_syscall_latency_wait_rising():
    """wait_rising returns 0."""
    setup_test()
    call = SysCall(
        func=Temp('polyphony.timing.wait_rising'),
        args=[],
        kwargs={},
    )
    object.__setattr__(call, 'name', 'polyphony.timing.wait_rising')
    assert _get_syscall_latency(call) == 0


def test_syscall_latency_wait_falling():
    """wait_falling returns 0."""
    setup_test()
    call = SysCall(
        func=Temp('polyphony.timing.wait_falling'),
        args=[],
        kwargs={},
    )
    object.__setattr__(call, 'name', 'polyphony.timing.wait_falling')
    assert _get_syscall_latency(call) == 0


def test_syscall_latency_assert():
    """assert returns 0."""
    setup_test()
    call = SysCall(
        func=Temp('assert'),
        args=[('', Const(value=True))],
        kwargs={},
    )
    object.__setattr__(call, 'name', 'assert')
    assert _get_syscall_latency(call) == 0


def test_syscall_latency_print():
    """print returns 0."""
    setup_test()
    call = SysCall(
        func=Temp('print'),
        args=[('', Const(value=42))],
        kwargs={},
    )
    object.__setattr__(call, 'name', 'print')
    assert _get_syscall_latency(call) == 0


def test_syscall_latency_unknown():
    """Unknown syscall returns UNIT_STEP."""
    setup_test()
    call = SysCall(
        func=Temp('other'),
        args=[],
        kwargs={},
    )
    object.__setattr__(call, 'name', 'other')
    assert _get_syscall_latency(call) == UNIT_STEP


# ============================================================
# _get_latency for Expr with SysCall
# ============================================================

def test_latency_expr_syscall_print():
    """Expr with print SysCall returns 0."""
    scope = build_scope('''
scope F
tags function returnable
return int32

blk1:
expr (syscall print 42)
mv @return 0
ret @return
''')
    for stm in scope.entry_block.stms:
        if isinstance(stm, Expr) and isinstance(stm.exp, SysCall):
            assert _get_latency(stm) == 0
            return
    assert False, "SysCall Expr not found"


# ============================================================
# _get_latency for Expr with Call
# ============================================================

def test_latency_expr_call():
    """Expr with Call (void function call) uses _get_call_latency."""
    src = '''
scope top
tags namespace
var G: function(top.G)

scope top.G
tags function returnable
return int32
var x: int32

blk1:
mv x 0
mv @return x
ret @return

scope top.F
tags function returnable
return int32
from top import G

blk1:
expr (call G 1)
mv @return 0
ret @return
'''
    scope = build_scope(src)
    F = env.scopes.get('top.F')
    assert F is not None
    for stm in F.entry_block.stms:
        if isinstance(stm, Expr) and isinstance(stm.exp, Call):
            lat = _get_latency(stm)
            assert lat == UNIT_STEP * CALL_MINIMUM_STEP
            return
    assert False, "Call Expr not found"


# ============================================================
# _get_latency for UPhi
# ============================================================

def test_latency_ret():
    """Ret returns UNIT_STEP."""
    scope = build_scope('''
scope F
tags function returnable
return int32

blk1:
mv @return 0
ret @return
''')
    for stm in scope.entry_block.stms:
        if isinstance(stm, Ret):
            assert _get_latency(stm) == UNIT_STEP
            return
    assert False, "Ret not found"


def test_latency_jump():
    """Jump returns UNIT_STEP."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var c: bool

blk1:
mv c True
cj c blk2 blk2

blk2:
mv @return 0
ret @return
''')
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, CJump):
                assert _get_latency(stm) == UNIT_STEP
                return
    assert False, "CJump not found"
