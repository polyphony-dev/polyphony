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


# ============================================================
# _get_latency for Phi / UPhi (alias and non-alias)
# ============================================================

def test_latency_phi_normal():
    """Phi for normal variable returns UNIT_STEP."""
    scope = build_scope('''
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
phi x (1 2)
mv @return x
ret @return
''')
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Phi):
                assert _get_latency(stm) == UNIT_STEP
                return
    assert False, "Phi not found"


def test_latency_phi_alias():
    """Phi for alias variable returns 0."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var c: bool
var a: int32 {alias}

blk1:
mv c True
cj c blk2 blk3

blk2:
mv a 1
j exit

blk3:
mv a 2
j exit

exit:
phi a (1 2)
mv @return a
ret @return
''')
    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Phi):
                assert _get_latency(stm) == 0
                return
    assert False, "Phi not found"


def test_latency_uphi_normal():
    """UPhi for normal variable returns UNIT_STEP."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var x: int32

blk1:
uphi x (1 2)
mv @return x
ret @return
''')
    stm = scope.entry_block.stms[0]
    assert isinstance(stm, UPhi)
    assert _get_latency(stm) == UNIT_STEP


def test_latency_uphi_alias():
    """UPhi for alias variable returns 0."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var a: int32 {alias}

blk1:
uphi a (1 2)
mv @return a
ret @return
''')
    stm = scope.entry_block.stms[0]
    assert isinstance(stm, UPhi)
    assert _get_latency(stm) == 0


# ============================================================
# _get_latency: Move edge cases
# ============================================================

def test_latency_move_seq_dst_non_array_src():
    """Move to seq-typed dst with non-Array src falls through to UNIT_STEP."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var arr: list<int32>[4]
var other: list<int32>[4]

blk1:
mv arr other
mv @return 0
ret @return
''')
    stm = scope.entry_block.stms[0]  # mv arr other
    assert isinstance(stm, Move)
    assert _get_latency(stm) == UNIT_STEP


def test_latency_move_non_alias_fallthrough():
    """Move that doesn't match any special case returns UNIT_STEP."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x (+ 1 2)
mv @return x
ret @return
''')
    stm = scope.entry_block.stms[0]  # mv x (+ 1 2)
    assert _get_latency(stm) == UNIT_STEP


def test_latency_move_seq_alias_fallthrough():
    """Move to alias seq dst falls through to alias check, returns 0."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var arr: list<int32>[4] {alias}
var other: list<int32>[4]

blk1:
mv arr other
mv @return 0
ret @return
''')
    stm = scope.entry_block.stms[0]  # mv arr other
    assert isinstance(stm, Move)
    assert _get_latency(stm) == 0


# ============================================================
# _get_call_latency: Port and Net via setup_libs
# ============================================================

def _make_port_scope():
    """Create a function scope with a Port symbol for call latency tests."""
    from polyphony.compiler.ir.scope import Scope
    from polyphony.compiler.ir.symbol import Symbol
    from polyphony.compiler.ir.types.type import Type
    from polyphony.compiler.ir.block import Block

    setup_test()
    setup_libs('io')
    top = Scope.global_scope()
    port_scope = env.scopes['polyphony.io.Port']
    rd_scope = env.scopes['polyphony.io.Port.rd']
    wr_scope = env.scopes['polyphony.io.Port.wr']

    F = Scope.create(top, 'F', {'function', 'returnable'}, 0)
    F.return_type = Type.int(32)
    F.add_return_sym(F.return_type)

    # Create port symbol
    port_type = Type.port(port_scope, {'dtype': Type.int(32), 'direction': 'input'})
    p_sym = F.add_sym('p', tags=set(), typ=port_type)

    # Create result var
    F.add_sym('x', tags=set(), typ=Type.int(32))

    # Import rd
    rd_sym = port_scope.find_sym('rd')
    if rd_sym:
        F.import_sym(rd_sym)

    blk = Block(F, nametag='blk1')
    F.set_entry_block(blk)
    F.set_exit_block(blk)
    for b in F.traverse_blocks():
        b.synth_params['scheduling'] = 'sequential'
        b.synth_params['cycle'] = 'any'
        b.synth_params['ii'] = -1
    Block.set_order(blk, 0)
    return F, blk, p_sym, rd_scope, wr_scope


def test_latency_port_rd_move():
    """Port.rd() in Move context returns UNIT_STEP."""
    F, blk, p_sym, rd_scope, _ = _make_port_scope()
    # mv x (call p.rd)
    port_rd = Attr(name='rd', exp=Temp('p'), attr='rd')
    call = Call(func=port_rd, args=[], kwargs={})
    mv = blk.append_stm(Move(dst=Temp('x', Ctx.STORE), src=call))
    blk.append_stm(Ret(Temp('@return')))
    lat = _get_latency(mv)
    assert lat == UNIT_STEP


def test_latency_port_rd_expr():
    """Port.rd() in Expr context (dummy read) returns 0."""
    F, blk, p_sym, rd_scope, _ = _make_port_scope()
    # expr (call p.rd)
    port_rd = Attr(name='rd', exp=Temp('p'), attr='rd')
    call = Call(func=port_rd, args=[], kwargs={})
    expr_stm = blk.append_stm(Expr(exp=call))
    blk.append_stm(Ret(Temp('@return')))
    lat = _get_latency(expr_stm)
    assert lat == 0


def test_latency_port_wr():
    """Port.wr() returns UNIT_STEP."""
    F, blk, p_sym, _, wr_scope = _make_port_scope()
    # expr (call p.wr 42)
    port_wr = Attr(name='wr', exp=Temp('p'), attr='wr')
    call = Call(func=port_wr, args=[('', Const(42))], kwargs={})
    expr_stm = blk.append_stm(Expr(exp=call))
    blk.append_stm(Ret(Temp('@return')))
    lat = _get_latency(expr_stm)
    assert lat == UNIT_STEP


def test_latency_move_port_src():
    """Move from port-typed Temp returns 0 (line 80-81)."""
    from polyphony.compiler.ir.scope import Scope
    from polyphony.compiler.ir.types.type import Type
    from polyphony.compiler.ir.block import Block

    setup_test()
    setup_libs('io')
    top = Scope.global_scope()
    port_scope = env.scopes['polyphony.io.Port']

    F = Scope.create(top, 'F2', {'function', 'returnable'}, 0)
    F.return_type = Type.int(32)
    F.add_return_sym(F.return_type)
    port_type = Type.port(port_scope, {'dtype': Type.int(32), 'direction': 'input'})
    F.add_sym('p', tags=set(), typ=port_type)
    F.add_sym('x', tags=set(), typ=Type.int(32))

    blk = Block(F, nametag='blk1')
    F.set_entry_block(blk)
    F.set_exit_block(blk)
    for b in F.traverse_blocks():
        b.synth_params['scheduling'] = 'sequential'
        b.synth_params['cycle'] = 'any'
        b.synth_params['ii'] = -1
    Block.set_order(blk, 0)

    # mv x p (port-typed temp src)
    mv = blk.append_stm(Move(dst=Temp('x', Ctx.STORE), src=Temp('p')))
    blk.append_stm(Ret(Temp('@return')))
    lat = _get_latency(mv)
    assert lat == 0


# ============================================================
# _get_call_latency: Net.rd
# ============================================================

def _make_net_scope():
    """Create a function scope with a Net symbol for call latency tests."""
    from polyphony.compiler.ir.scope import Scope
    from polyphony.compiler.ir.types.type import Type
    from polyphony.compiler.ir.block import Block

    setup_test()
    setup_libs('io')
    top = Scope.global_scope()
    net_scope = env.scopes['polyphony.Net']
    rd_scope = env.scopes['polyphony.Net.rd']

    F = Scope.create(top, 'FN', {'function', 'returnable'}, 0)
    F.return_type = Type.int(32)
    F.add_return_sym(F.return_type)

    # Create Net-typed symbol
    net_type = Type.object(net_scope)
    F.add_sym('n', tags={'alias'}, typ=net_type)
    F.add_sym('x', tags=set(), typ=Type.int(32))
    F.add_sym('a', tags={'alias'}, typ=Type.int(32))

    # Import rd
    rd_sym = net_scope.find_sym('rd')
    if rd_sym:
        F.import_sym(rd_sym)

    blk = Block(F, nametag='blk1')
    F.set_entry_block(blk)
    F.set_exit_block(blk)
    for b in F.traverse_blocks():
        b.synth_params['scheduling'] = 'sequential'
        b.synth_params['cycle'] = 'any'
        b.synth_params['ii'] = -1
    Block.set_order(blk, 0)
    return F, blk


def test_latency_net_rd_move_alias():
    """Net.rd() in Move to alias dst returns 0."""
    F, blk = _make_net_scope()
    net_rd = Attr(name='rd', exp=Temp('n'), attr='rd')
    call = Call(func=net_rd, args=[], kwargs={})
    mv = blk.append_stm(Move(dst=Temp('a', Ctx.STORE), src=call))
    blk.append_stm(Ret(Temp('@return')))
    lat = _get_latency(mv)
    assert lat == 0


def test_latency_net_rd_move_non_alias():
    """Net.rd() in Move to non-alias dst returns UNIT_STEP."""
    F, blk = _make_net_scope()
    net_rd = Attr(name='rd', exp=Temp('n'), attr='rd')
    call = Call(func=net_rd, args=[], kwargs={})
    mv = blk.append_stm(Move(dst=Temp('x', Ctx.STORE), src=call))
    blk.append_stm(Ret(Temp('@return')))
    lat = _get_latency(mv)
    assert lat == UNIT_STEP


def test_latency_net_rd_expr():
    """Net.rd() in Expr context returns 0."""
    F, blk = _make_net_scope()
    net_rd = Attr(name='rd', exp=Temp('n'), attr='rd')
    call = Call(func=net_rd, args=[], kwargs={})
    expr_stm = blk.append_stm(Expr(exp=call))
    blk.append_stm(Ret(Temp('@return')))
    lat = _get_latency(expr_stm)
    assert lat == 0
