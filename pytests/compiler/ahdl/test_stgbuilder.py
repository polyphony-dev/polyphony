"""Tests for STGBuilder, StateBuilder, ScheduledItemQueue, and helpers."""
import sys
import dataclasses
from polyphony.compiler.ahdl.ahdl import (
    AHDL_BLOCK, AHDL_CONST, AHDL_IF, AHDL_MOVE, AHDL_NOP, AHDL_OP,
    AHDL_PROCCALL, AHDL_SEQ, AHDL_SUBSCRIPT, AHDL_TRANSITION,
    AHDL_TRANSITION_IF, AHDL_VAR, AHDL_MEMVAR, State,
)
from polyphony.compiler.ahdl.signal import Signal
from polyphony.compiler.ahdl.stg import STG
from polyphony.compiler.ahdl.stgbuilder import (
    ScheduledItemQueue, STGBuilder, _signal_width, _tags_from_sym,
)
from polyphony.compiler.ahdl.hdlmodule import HDLModule
from polyphony.compiler.ahdl.hdlscope import HDLScope
from polyphony.compiler.ir.ir import Ctx
from polyphony.compiler.ir.irreader import IrReader as IrParser
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


# ============================================================
# Helpers
# ============================================================

def build_scope(src):
    setup_test()
    parser = IrParser(src)
    parser.parse_scope()
    for name in parser.sources:
        return env.scopes[name]


def make_hdlmodule(scope):
    """Create a minimal HDLModule registered in env."""
    hdl = HDLModule(scope, scope.base_name, scope.base_name)
    env.append_hdlscope(hdl)
    return hdl


def make_signal(hdlscope, name, width=1, tags=None):
    """Create a signal via hdlscope.gen_sig."""
    if tags is None:
        tags = {'reg'}
    return hdlscope.gen_sig(name, width, tags)


# ============================================================
# ScheduledItemQueue
# ============================================================

def test_scheduled_item_queue_push_pop_ordered():
    """Items are popped in ascending sched_time order."""
    q = ScheduledItemQueue()
    q.push(2, 'item_b', tag='')
    q.push(0, 'item_a', tag='')
    q.push(1, 'item_c', tag='')
    result = list(q.pop())
    times = [t for t, _ in result]
    assert times == [0, 1, 2]
    assert result[0][1] == [('item_a', '')]
    assert result[1][1] == [('item_c', '')]
    assert result[2][1] == [('item_b', '')]


def test_scheduled_item_queue_same_time():
    """Multiple items at the same sched_time are grouped together."""
    q = ScheduledItemQueue()
    q.push(1, 'a', tag='x')
    q.push(1, 'b', tag='y')
    result = list(q.pop())
    assert len(result) == 1
    assert result[0][0] == 1
    items = result[0][1]
    assert len(items) == 2
    assert items[0] == ('a', 'x')
    assert items[1] == ('b', 'y')


def test_scheduled_item_queue_negative_one_goes_to_end():
    """sched_time=-1 is stored at sys.maxsize (end of queue)."""
    q = ScheduledItemQueue()
    q.push(0, 'first', tag='')
    q.push(-1, 'last', tag='')
    q.push(100, 'middle', tag='')
    result = list(q.pop())
    times = [t for t, _ in result]
    assert times == [0, 100, sys.maxsize]
    assert result[-1][1] == [('last', '')]


def test_scheduled_item_queue_peek():
    """peek returns items at a given sched_time without consuming them."""
    q = ScheduledItemQueue()
    q.push(5, 'a', tag='')
    q.push(5, 'b', tag='')
    peeked = q.peek(5)
    assert len(peeked) == 2
    # Items are still in the queue after peek
    result = list(q.pop())
    assert len(result) == 1
    assert len(result[0][1]) == 2


def test_scheduled_item_queue_empty():
    """Popping an empty queue yields nothing."""
    q = ScheduledItemQueue()
    result = list(q.pop())
    assert result == []


# ============================================================
# STGBuilder._resolve_transition
# ============================================================

def _make_state_with_transition(stg, name, target_name=''):
    """Helper to create a State containing a single AHDL_TRANSITION."""
    trans = AHDL_TRANSITION(target_name)
    blk = AHDL_BLOCK(name, (trans,))
    return State(name, blk, 0, stg)


def test_resolve_transition_empty_target():
    """Empty AHDL_TRANSITION resolves to the next_state."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 1
ret @return
''')
    hdl = make_hdlmodule(scope)
    stg = STG('test', None, hdl)
    s1 = _make_state_with_transition(stg, 'S1', '')  # empty target
    s2 = _make_state_with_transition(stg, 'S2', '')

    builder = STGBuilder()
    builder._resolve_transition(s1, s2, {})

    trans = s1.block.codes[-1]
    assert isinstance(trans, AHDL_TRANSITION)
    assert trans.target_name == 'S2'


def test_resolve_transition_named_target():
    """Named AHDL_TRANSITION resolves to the blk2states target."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 1
ret @return
''')
    hdl = make_hdlmodule(scope)
    stg = STG('test', None, hdl)
    target_state = _make_state_with_transition(stg, 'TARGET_S0', '')

    s1_trans = AHDL_TRANSITION('blk_target')
    s1_blk = AHDL_BLOCK('S1', (s1_trans,))
    s1 = State('S1', s1_blk, 0, stg)

    s2 = _make_state_with_transition(stg, 'S2', '')

    blk2states = {'blk_target': [target_state]}
    builder = STGBuilder()
    builder._resolve_transition(s1, s2, blk2states)

    trans = s1.block.codes[-1]
    assert isinstance(trans, AHDL_TRANSITION)
    assert trans.target_name == 'TARGET_S0'


def test_resolve_transition_if():
    """AHDL_TRANSITION_IF resolves each branch to the correct state."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 1
ret @return
''')
    hdl = make_hdlmodule(scope)
    stg = STG('test', None, hdl)

    target_a = _make_state_with_transition(stg, 'A_S0', '')
    target_b = _make_state_with_transition(stg, 'B_S0', '')

    cond = AHDL_CONST(1)
    conds = (cond, AHDL_CONST(1))
    blocks = (
        AHDL_BLOCK('', (AHDL_TRANSITION('blk_a'),)),
        AHDL_BLOCK('', (AHDL_TRANSITION('blk_b'),)),
    )
    trans_if = AHDL_TRANSITION_IF(conds, blocks)
    s1_blk = AHDL_BLOCK('S1', (trans_if,))
    s1 = State('S1', s1_blk, 0, stg)
    s2 = _make_state_with_transition(stg, 'S2', '')

    blk2states = {'blk_a': [target_a], 'blk_b': [target_b]}
    builder = STGBuilder()
    builder._resolve_transition(s1, s2, blk2states)

    code = s1.block.codes[-1]
    assert isinstance(code, AHDL_TRANSITION_IF)
    assert code.blocks[0].codes[-1].target_name == 'A_S0'
    assert code.blocks[1].codes[-1].target_name == 'B_S0'


# ============================================================
# _signal_width
# ============================================================

def test_signal_width_int():
    """int type returns correct bit width."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 1
ret @return
''')
    sym = scope.find_sym('x')
    assert _signal_width(sym) == 32


def test_signal_width_bool():
    """bool type returns width 1."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var c: bool

blk1:
mv c True
ret @return
''')
    sym = scope.find_sym('c')
    assert _signal_width(sym) == 1


def test_signal_width_int8():
    """int8 type returns width 8."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var y: int8

blk1:
mv y 42
ret @return
''')
    sym = scope.find_sym('y')
    assert _signal_width(sym) == 8


# ============================================================
# _tags_from_sym
# ============================================================

def test_tags_from_sym_int_signed():
    """Signed int symbol gets 'int', 'reg', 'initializable' tags."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 1
ret @return
''')
    sym = scope.find_sym('x')
    tags = _tags_from_sym(sym)
    assert 'int' in tags
    assert 'reg' in tags
    assert 'initializable' in tags


def test_tags_from_sym_bool():
    """Bool symbol gets 'reg', 'initializable' but not 'int'."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var c: bool

blk1:
mv c True
ret @return
''')
    sym = scope.find_sym('c')
    tags = _tags_from_sym(sym)
    assert 'reg' in tags
    assert 'initializable' in tags
    assert 'int' not in tags


def test_tags_from_sym_unsigned_int():
    """Unsigned int symbol does not get 'int' tag."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var u: bit8

blk1:
mv u 1
ret @return
''')
    sym = scope.find_sym('u')
    tags = _tags_from_sym(sym)
    assert 'int' not in tags
    assert 'reg' in tags


def test_tags_from_sym_condition():
    """Condition symbol gets 'condition' tag."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var cnd0: bool {condition}

blk1:
mv cnd0 True
ret @return
''')
    sym = scope.find_sym('cnd0')
    tags = _tags_from_sym(sym)
    assert 'condition' in tags


def test_tags_from_sym_int_alias():
    """Int alias symbol gets 'net' instead of 'reg'."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var a: int32 {alias}

blk1:
mv a 1
ret @return
''')
    sym = scope.find_sym('a')
    tags = _tags_from_sym(sym)
    assert 'net' in tags
    assert 'reg' not in tags
    assert 'int' in tags


def test_tags_from_sym_bool_alias():
    """Bool alias symbol gets 'net' instead of 'reg'."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var b: bool {alias}

blk1:
mv b True
ret @return
''')
    sym = scope.find_sym('b')
    tags = _tags_from_sym(sym)
    assert 'net' in tags
    assert 'reg' not in tags
    assert 'initializable' not in tags


def test_tags_from_sym_induction():
    """Induction symbol gets 'induction' tag."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var i: int32 {induction}

blk1:
mv i 0
ret @return
''')
    sym = scope.find_sym('i')
    tags = _tags_from_sym(sym)
    assert 'induction' in tags
    assert 'reg' in tags
    assert 'int' in tags


def test_tags_from_sym_field():
    """Field symbol gets 'field' tag."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var f: int32 {field}

blk1:
mv f 1
ret @return
''')
    sym = scope.find_sym('f')
    tags = _tags_from_sym(sym)
    assert 'field' in tags
    assert 'reg' in tags
    assert 'int' in tags


def test_tags_from_sym_tuple_signed():
    """Tuple with signed int element gets 'int' and 'regarray'."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var t: tuple<int32>[4]

blk1:
ret @return
''')
    sym = scope.find_sym('t')
    tags = _tags_from_sym(sym)
    assert 'int' in tags
    assert 'regarray' in tags


def test_tags_from_sym_tuple_unsigned():
    """Tuple with unsigned element gets 'regarray' but not 'int'."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var t: tuple<bit8>[4]

blk1:
ret @return
''')
    sym = scope.find_sym('t')
    tags = _tags_from_sym(sym)
    assert 'int' not in tags
    assert 'regarray' in tags


def test_tags_from_sym_tuple_alias():
    """Tuple alias symbol gets 'netarray'."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var t: tuple<int32>[4] {alias}

blk1:
ret @return
''')
    sym = scope.find_sym('t')
    tags = _tags_from_sym(sym)
    assert 'netarray' in tags
    assert 'regarray' not in tags
    assert 'int' in tags


def test_tags_from_sym_list_signed():
    """List with signed int element gets 'int' and 'regarray'."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var l: list<int32>[8]

blk1:
ret @return
''')
    sym = scope.find_sym('l')
    tags = _tags_from_sym(sym)
    assert 'int' in tags
    assert 'regarray' in tags


def test_tags_from_sym_list_unsigned():
    """List with unsigned element gets 'regarray' but not 'int'."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var l: list<bit8>[8]

blk1:
ret @return
''')
    sym = scope.find_sym('l')
    tags = _tags_from_sym(sym)
    assert 'int' not in tags
    assert 'regarray' in tags


def test_tags_from_sym_initializable_only_for_reg():
    """'initializable' tag is only added when 'reg' is present."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var r: int32
var n: int32 {alias}

blk1:
mv r 1
mv n 2
ret @return
''')
    reg_sym = scope.find_sym('r')
    net_sym = scope.find_sym('n')
    reg_tags = _tags_from_sym(reg_sym)
    net_tags = _tags_from_sym(net_sym)
    assert 'initializable' in reg_tags
    assert 'initializable' not in net_tags


# ============================================================
# _signal_width additional tests
# ============================================================

def test_signal_width_tuple():
    """Tuple type returns (element_width, length) tuple."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var t: tuple<int32>[4]

blk1:
ret @return
''')
    sym = scope.find_sym('t')
    assert _signal_width(sym) == (32, 4)


def test_signal_width_list():
    """List type returns (element_width, length) tuple."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var l: list<int16>[8]

blk1:
ret @return
''')
    sym = scope.find_sym('l')
    assert _signal_width(sym) == (16, 8)


def test_signal_width_condition():
    """Condition symbol returns width 1."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var c: bool {condition}

blk1:
mv c True
ret @return
''')
    sym = scope.find_sym('c')
    assert _signal_width(sym) == 1


# ============================================================
# AHDLTranslator.visit_Const
# ============================================================

def test_visit_const_int():
    """Const with int value produces AHDL_CONST with same value."""
    from polyphony.compiler.ir.ir import Const
    from polyphony.compiler.ahdl.stgbuilder import AHDLTranslator

    scope = build_scope('''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 1
ret @return
''')
    hdl = make_hdlmodule(scope)
    stg = STG('test', None, hdl)

    class DummyHost:
        pass

    translator = AHDLTranslator('test', DummyHost(), scope)
    result = translator.visit_Const(Const(value=42))
    assert isinstance(result, AHDL_CONST)
    assert result.value == 42


def test_visit_const_none():
    """Const with None value produces AHDL_SYMBOL('bz)."""
    from polyphony.compiler.ir.ir import Const
    from polyphony.compiler.ahdl.stgbuilder import AHDLTranslator
    from polyphony.compiler.ahdl.ahdl import AHDL_SYMBOL

    scope = build_scope('''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 1
ret @return
''')
    hdl = make_hdlmodule(scope)

    class DummyHost:
        pass

    translator = AHDLTranslator('test', DummyHost(), scope)
    result = translator.visit_Const(Const(value=None))
    assert isinstance(result, AHDL_SYMBOL)
    assert result.name == "'bz"


def test_visit_const_bool():
    """Const with bool value produces AHDL_CONST with int value."""
    from polyphony.compiler.ir.ir import Const
    from polyphony.compiler.ahdl.stgbuilder import AHDLTranslator

    scope = build_scope('''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 1
ret @return
''')
    hdl = make_hdlmodule(scope)

    class DummyHost:
        pass

    translator = AHDLTranslator('test', DummyHost(), scope)

    result_true = translator.visit_Const(Const(value=True))
    assert isinstance(result_true, AHDL_CONST)
    assert result_true.value == 1

    result_false = translator.visit_Const(Const(value=False))
    assert isinstance(result_false, AHDL_CONST)
    assert result_false.value == 0


# ============================================================
# STG basic operations
# ============================================================

def test_stg_new_state_and_add():
    """STG.new_state creates a State, add_states adds it."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 1
ret @return
''')
    hdl = make_hdlmodule(scope)
    stg = STG('test_stg', None, hdl)

    blk = AHDL_BLOCK('S0', (AHDL_TRANSITION(''),))
    state = stg.new_state('S0', blk, 0)
    assert isinstance(state, State)
    assert state.name == 'S0'
    assert state.stg is stg

    stg.add_states([state])
    assert stg.has_state('S0')
    assert stg.get_state('S0') is state
    assert len(stg.states) == 1


def test_stg_is_main():
    """STG without parent is main."""
    scope = build_scope('''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 1
ret @return
''')
    hdl = make_hdlmodule(scope)
    main_stg = STG('main', None, hdl)
    child_stg = STG('child', main_stg, hdl)
    assert main_stg.is_main()
    assert not child_stg.is_main()


# ============================================================
# AHDLTranslator / AHDLCombTranslator visit method presence
# ============================================================

from polyphony.compiler.ahdl.stgbuilder import AHDLTranslator, AHDLCombTranslator

TRANSLATOR_METHODS = [
    'UnOp', 'BinOp', 'RelOp', 'CondOp',
    'Call', 'New', 'SysCall', 'Const',
    'MRef', 'MStore', 'Array', 'Temp', 'Attr',
    'Expr', 'CJump', 'Jump', 'MCJump', 'Ret', 'Move', 'Phi',
]

COMB_METHODS = [
    'Call', 'SysCall', 'New', 'Temp', 'Attr',
    'MRef', 'MStore', 'Array',
    'Expr', 'CJump', 'MCJump', 'Jump', 'Ret', 'Move', 'Phi',
    'CExpr', 'CMove',
]


def test_ahdl_translator_has_visit_methods():
    """AHDLTranslator has PascalCase visit methods for all IR types."""
    for name in TRANSLATOR_METHODS:
        method = getattr(AHDLTranslator, f'visit_{name}', None)
        assert method is not None, f'Missing visit_{name} on AHDLTranslator'


def test_ahdl_comb_translator_has_visit_methods():
    """AHDLCombTranslator has PascalCase visit methods for all IR types."""
    for name in COMB_METHODS:
        method = getattr(AHDLCombTranslator, f'visit_{name}', None)
        assert method is not None, f'Missing visit_{name} on AHDLCombTranslator'


def test_ahdl_translator_inherits_irvisitor_methods():
    """AHDLTranslator inherits base visitor methods from IrVisitor."""
    for name in ['UnOp', 'BinOp', 'RelOp', 'CondOp', 'Const', 'Temp', 'Attr']:
        assert hasattr(AHDLTranslator, f'visit_{name}'), f'Missing visit_{name} on AHDLTranslator'
