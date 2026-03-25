import os

RUNTIME_H = os.path.join(
    os.path.dirname(__file__),
    '../../../../polyphony/compiler/target/csim/runtime_template.h',
)


def test_runtime_template_exists():
    assert os.path.isfile(RUNTIME_H)


def test_runtime_template_has_mask():
    with open(RUNTIME_H) as f:
        src = f.read()
    assert 'mask' in src
    assert 'int64_t' in src


from unittest.mock import MagicMock
from polyphony.compiler.target.csim.csimgen import AHDLToCTranspiler
from polyphony.compiler.ahdl.ahdl import (
    AHDL_CONST, AHDL_VAR, AHDL_OP, AHDL_IF_EXP,
    AHDL_MEMVAR, AHDL_SUBSCRIPT, AHDL_FUNCALL, AHDL_SYMBOL,
    AHDL_MOVE, AHDL_ASSIGN, AHDL_CONNECT,
    AHDL_BLOCK, AHDL_IF, AHDL_CASE, AHDL_CASE_ITEM, AHDL_SEQ,
    AHDL_EVENT_TASK, AHDL_PROCCALL, AHDL_NOP, AHDL_MODULECALL, AHDL_TRANSITION,
    Ctx,
)


def _make_signal(name, width, tags):
    """Create a mock Signal with Tagged-compatible is_xxx() methods."""
    sig = MagicMock()
    sig.name = name
    sig.width = width
    sig.tags = set(tags)
    sig.is_reg = lambda: 'reg' in sig.tags
    sig.is_net = lambda: 'net' in sig.tags
    sig.is_regarray = lambda: 'regarray' in sig.tags
    sig.is_netarray = lambda: 'netarray' in sig.tags
    sig.is_constant = lambda: 'constant' in sig.tags
    sig.is_rom = lambda: 'rom' in sig.tags
    sig.is_input = lambda: 'input' in sig.tags
    sig.is_output = lambda: 'output' in sig.tags
    sig.is_int = lambda: 'int' in sig.tags
    sig.is_initializable = lambda: False
    sig.init_value = 0
    sig.is_subscope = lambda: 'subscope' in sig.tags
    return sig


def _make_hdlscope(signals, constants=None, subscopes=None):
    scope = MagicMock()

    def get_signals(include_tags=None, exclude_tags=None):
        result = []
        for sig in signals:
            if exclude_tags and exclude_tags & sig.tags:
                continue
            if include_tags and not (include_tags & sig.tags):
                continue
            result.append(sig)
        return result

    scope.get_signals = get_signals
    scope.constants = constants or {}
    scope.subscopes = subscopes or {}
    scope.name = 'test_module'
    return scope


def test_assign_signal_ids_scalar_reg_and_net():
    reg_sig = _make_signal('state', 8, {'reg'})
    net_sig = _make_signal('sum', 16, {'net'})
    hdlscope = _make_hdlscope([reg_sig, net_sig])
    tp = AHDLToCTranspiler()
    sig_map, port_map, sig_count = tp.assign_signal_ids(hdlscope)
    assert sig_map['state'] == 0
    assert sig_map['state_next'] == 1
    assert sig_map['sum'] == 2
    assert sig_count == 3
    assert port_map == {}


def test_assign_signal_ids_with_ports():
    in_sig = _make_signal('a', 32, {'net', 'input'})
    out_sig = _make_signal('result', 32, {'reg', 'output'})
    hdlscope = _make_hdlscope([in_sig, out_sig])
    tp = AHDLToCTranspiler()
    sig_map, port_map, sig_count = tp.assign_signal_ids(hdlscope)
    assert port_map['a'] == sig_map['a']
    assert port_map['result'] == sig_map['result']


def test_assign_signal_ids_regarray():
    arr_sig = _make_signal('mem', (32, 4), {'regarray'})
    hdlscope = _make_hdlscope([arr_sig])
    tp = AHDLToCTranspiler()
    sig_map, port_map, sig_count = tp.assign_signal_ids(hdlscope)
    assert sig_map['mem'] == 0
    assert sig_map['mem_next'] == 4
    assert sig_count == 8


def test_assign_signal_ids_netarray():
    arr_sig = _make_signal('wires', (16, 3), {'netarray'})
    hdlscope = _make_hdlscope([arr_sig])
    tp = AHDLToCTranspiler()
    sig_map, port_map, sig_count = tp.assign_signal_ids(hdlscope)
    assert sig_map['wires'] == 0
    assert sig_count == 3


def test_assign_signal_ids_skip_constant_and_rom():
    const_sig = _make_signal('PARAM', 32, {'constant'})
    rom_sig = _make_signal('rom0', 32, {'rom'})
    reg_sig = _make_signal('x', 8, {'reg'})
    hdlscope = _make_hdlscope([const_sig, rom_sig, reg_sig])
    hdlscope.constants = {const_sig: 42}
    tp = AHDLToCTranspiler()
    sig_map, port_map, sig_count = tp.assign_signal_ids(hdlscope)
    assert 'PARAM' not in sig_map
    assert 'rom0' not in sig_map
    assert sig_map['x'] == 0
    assert sig_count == 2


def test_emit_signal_defines():
    reg_sig = _make_signal('fsm_state', 8, {'reg'})
    net_sig = _make_signal('sum', 16, {'net'})
    in_sig = _make_signal('a', 32, {'net', 'input'})
    hdlscope = _make_hdlscope([reg_sig, net_sig, in_sig])
    tp = AHDLToCTranspiler()
    tp.assign_signal_ids(hdlscope)
    header = tp.emit_signal_defines()
    assert '#define S_fsm_state ' in header
    assert '#define S_fsm_state_next ' in header
    assert '#define S_sum ' in header
    assert '#define S_a ' in header
    assert '#define S_NUM_SIGNALS ' in header


def test_emit_signal_defines_array():
    arr_sig = _make_signal('mem', (32, 4), {'regarray'})
    hdlscope = _make_hdlscope([arr_sig])
    tp = AHDLToCTranspiler()
    tp.assign_signal_ids(hdlscope)
    header = tp.emit_signal_defines()
    assert '#define S_mem ' in header
    assert '#define S_mem_next ' in header
    assert 'S_mem_LEN' in header
    # Check the value after padding
    for line in header.splitlines():
        if 'S_mem_LEN' in line:
            assert line.split()[-1] == '4'


def _setup_transpiler_with_signals(*signals):
    hdlscope = _make_hdlscope(list(signals))
    tp = AHDLToCTranspiler()
    tp.assign_signal_ids(hdlscope)
    return tp


def _make_var(sig, ctx=None):
    if ctx is None:
        ctx = Ctx.LOAD
    return AHDL_VAR((sig,), ctx)


# --- Task 4: Expression visitors (CONST, VAR, OP, IF_EXP) ---


def test_visit_const_int():
    tp = AHDLToCTranspiler()
    result = tp.visit(AHDL_CONST(42))
    assert result == '42'


def test_visit_const_bz():
    tp = AHDLToCTranspiler()
    result = tp.visit(AHDL_CONST("'bz"))
    assert result == '0'


def test_visit_var_load_reg():
    reg = _make_signal('x', 8, {'reg'})
    tp = _setup_transpiler_with_signals(reg)
    result = tp.visit(_make_var(reg, Ctx.LOAD))
    assert result == 's[S_x]'


def test_visit_var_store_reg():
    reg = _make_signal('x', 8, {'reg'})
    tp = _setup_transpiler_with_signals(reg)
    result = tp.visit(_make_var(reg, Ctx.STORE))
    assert result == 's[S_x_next]'


def test_visit_var_load_net():
    net = _make_signal('y', 8, {'net'})
    tp = _setup_transpiler_with_signals(net)
    result = tp.visit(_make_var(net, Ctx.LOAD))
    assert result == 's[S_y]'


def test_visit_var_store_net():
    net = _make_signal('y', 8, {'net'})
    tp = _setup_transpiler_with_signals(net)
    result = tp.visit(_make_var(net, Ctx.STORE))
    assert result == 's[S_y]'


def test_visit_op_add():
    reg_a = _make_signal('a', 32, {'reg'})
    reg_b = _make_signal('b', 32, {'reg'})
    tp = _setup_transpiler_with_signals(reg_a, reg_b)
    node = AHDL_OP('Add', _make_var(reg_a), _make_var(reg_b))
    result = tp.visit(node)
    assert result == '(s[S_a] + s[S_b])'


def test_visit_op_unary_usub():
    reg_a = _make_signal('a', 32, {'reg'})
    tp = _setup_transpiler_with_signals(reg_a)
    node = AHDL_OP('USub', _make_var(reg_a))
    result = tp.visit(node)
    assert result == '(-s[S_a])'


def test_visit_op_relop_lt():
    reg_a = _make_signal('a', 32, {'reg'})
    tp = _setup_transpiler_with_signals(reg_a)
    node = AHDL_OP('Lt', _make_var(reg_a), AHDL_CONST(10))
    result = tp.visit(node)
    assert result == '(s[S_a] < 10)'


def test_visit_op_floordiv():
    reg_a = _make_signal('a', 32, {'reg'})
    reg_b = _make_signal('b', 32, {'reg'})
    tp = _setup_transpiler_with_signals(reg_a, reg_b)
    node = AHDL_OP('FloorDiv', _make_var(reg_a), _make_var(reg_b))
    result = tp.visit(node)
    assert result == 'floordiv(s[S_a], s[S_b])'


def test_visit_if_exp():
    cond_sig = _make_signal('cond', 1, {'reg'})
    x_sig = _make_signal('x', 32, {'reg'})
    tp = _setup_transpiler_with_signals(cond_sig, x_sig)
    node = AHDL_IF_EXP(
        _make_var(cond_sig),
        _make_var(x_sig),
        AHDL_CONST(0),
    )
    result = tp.visit(node)
    assert result == '(s[S_cond] ? s[S_x] : 0)'


# --- Task 5: Expression visitors (SUBSCRIPT, MEMVAR, FUNCALL, SYMBOL) ---


def test_visit_subscript_load():
    arr = _make_signal('mem', (32, 8), {'regarray'})
    tp = _setup_transpiler_with_signals(arr)
    memvar = AHDL_MEMVAR((arr,), Ctx.LOAD)
    node = AHDL_SUBSCRIPT(memvar, AHDL_CONST(3))
    result = tp.visit(node)
    assert result == 's[S_mem + 3]'


def test_visit_subscript_store():
    arr = _make_signal('mem', (32, 8), {'regarray'})
    tp = _setup_transpiler_with_signals(arr)
    memvar = AHDL_MEMVAR((arr,), Ctx.STORE)
    node = AHDL_SUBSCRIPT(memvar, AHDL_CONST(3))
    result = tp.visit(node)
    assert result == 's[S_mem_next + 3]'


def test_visit_subscript_dynamic_index():
    arr = _make_signal('mem', (32, 8), {'regarray'})
    idx = _make_signal('i', 8, {'reg'})
    tp = _setup_transpiler_with_signals(arr, idx)
    memvar = AHDL_MEMVAR((arr,), Ctx.LOAD)
    node = AHDL_SUBSCRIPT(memvar, _make_var(idx))
    result = tp.visit(node)
    assert result == 's[S_mem + s[S_i]]'


def test_visit_funcall():
    func_sig = _make_signal('rom0', 32, {'rom'})
    arg_sig = _make_signal('addr', 8, {'reg'})
    tp = _setup_transpiler_with_signals(arg_sig)
    func_var = AHDL_VAR((func_sig,), Ctx.LOAD)
    node = AHDL_FUNCALL(func_var, (_make_var(arg_sig),))
    result = tp.visit(node)
    assert result == 'func_rom0(s, s[S_addr])'


def test_visit_symbol_bz():
    tp = AHDLToCTranspiler()
    result = tp.visit(AHDL_SYMBOL("'bz"))
    assert result == '0'


def test_visit_symbol_unknown_raises():
    tp = AHDLToCTranspiler()
    try:
        tp.visit(AHDL_SYMBOL('unknown'))
        assert False, 'Expected NotImplementedError'
    except NotImplementedError:
        pass


# --- Task 6: Statement visitors (MOVE, ASSIGN, CONNECT) ---


def test_visit_move_reg():
    reg = _make_signal('x', 8, {'reg'})
    src_reg = _make_signal('y', 8, {'reg'})
    tp = _setup_transpiler_with_signals(reg, src_reg)
    tp._lines = []
    dst = _make_var(reg, Ctx.STORE)
    src = _make_var(src_reg, Ctx.LOAD)
    tp.visit(AHDL_MOVE(dst, src))
    code = '\n'.join(tp._lines)
    assert 's[S_x_next] = mask(' in code
    assert ', 8)' in code


def test_visit_move_net():
    net = _make_signal('z', 16, {'net'})
    tp = _setup_transpiler_with_signals(net)
    tp._lines = []
    dst = _make_var(net, Ctx.STORE)
    tp.visit(AHDL_MOVE(dst, AHDL_CONST(42)))
    code = '\n'.join(tp._lines)
    assert 's[S_z] = mask(' in code
    assert ', 16)' in code


def test_visit_assign_net_with_convergence():
    net = _make_signal('out', 32, {'net'})
    in_sig = _make_signal('inp', 32, {'net', 'input'})
    tp = _setup_transpiler_with_signals(net, in_sig)
    tp._lines = []
    dst = _make_var(net, Ctx.STORE)
    src = _make_var(in_sig, Ctx.LOAD)
    tp.visit(AHDL_ASSIGN(dst, src))
    code = '\n'.join(tp._lines)
    assert 'prev' in code.lower() or 'updated' in code


def test_visit_connect():
    a = _make_signal('a', 8, {'net'})
    b = _make_signal('b', 8, {'net'})
    tp = _setup_transpiler_with_signals(a, b)
    tp._lines = []
    tp.visit(AHDL_CONNECT(_make_var(a, Ctx.STORE), _make_var(b, Ctx.LOAD)))
    code = '\n'.join(tp._lines)
    assert 's[S_a]' in code
    assert 's[S_b]' in code


# --- Task 7: Control flow visitors (IF, CASE, BLOCK, SEQ) ---


def test_visit_block():
    reg = _make_signal('x', 8, {'reg'})
    tp = _setup_transpiler_with_signals(reg)
    tp._lines = []
    stm = AHDL_MOVE(_make_var(reg, Ctx.STORE), AHDL_CONST(1))
    block = AHDL_BLOCK('b', (stm,))
    tp.visit(block)
    code = '\n'.join(tp._lines)
    assert 's[S_x_next]' in code


def test_visit_if():
    cond = _make_signal('cond', 1, {'net'})
    x = _make_signal('x', 8, {'reg'})
    tp = _setup_transpiler_with_signals(cond, x)
    tp._lines = []
    then_stm = AHDL_MOVE(_make_var(x, Ctx.STORE), AHDL_CONST(1))
    else_stm = AHDL_MOVE(_make_var(x, Ctx.STORE), AHDL_CONST(0))
    then_block = AHDL_BLOCK('then', (then_stm,))
    else_block = AHDL_BLOCK('else', (else_stm,))
    node = AHDL_IF(
        (_make_var(cond), None),
        (then_block, else_block),
    )
    tp.visit(node)
    code = '\n'.join(tp._lines)
    assert 'if (s[S_cond])' in code
    assert 'else' in code


def test_visit_case():
    sel = _make_signal('sel', 8, {'reg'})
    x = _make_signal('x', 8, {'reg'})
    tp = _setup_transpiler_with_signals(sel, x)
    tp._lines = []
    item0 = AHDL_CASE_ITEM(AHDL_CONST(0), AHDL_BLOCK('c0', (AHDL_MOVE(_make_var(x, Ctx.STORE), AHDL_CONST(10)),)))
    item1 = AHDL_CASE_ITEM(AHDL_CONST(1), AHDL_BLOCK('c1', (AHDL_MOVE(_make_var(x, Ctx.STORE), AHDL_CONST(20)),)))
    node = AHDL_CASE(_make_var(sel), (item0, item1))
    tp.visit(node)
    code = '\n'.join(tp._lines)
    assert 'switch' in code
    assert 'case 0:' in code
    assert 'case 1:' in code
    assert 'break;' in code


def test_visit_seq_dispatches_to_inner():
    reg = _make_signal('x', 8, {'reg'})
    tp = _setup_transpiler_with_signals(reg)
    tp._lines = []
    inner = AHDL_MOVE(_make_var(reg, Ctx.STORE), AHDL_CONST(5))
    node = AHDL_SEQ(inner, 0, 1)
    tp.visit(node)
    code = '\n'.join(tp._lines)
    assert 's[S_x_next]' in code


# --- Task 8: Remaining visitors (EVENT_TASK, FUNCTION, PROCCALL, no-ops, fallbacks) ---


def test_visit_event_task_rising():
    clk = _make_signal('clk', 1, {'net', 'input'})
    x = _make_signal('x', 8, {'reg'})
    tp = _setup_transpiler_with_signals(clk, x)
    tp._lines = []
    stm = AHDL_MOVE(_make_var(x, Ctx.STORE), AHDL_CONST(1))
    node = AHDL_EVENT_TASK(((clk, 'rising'),), stm)
    tp.visit(node)
    code = '\n'.join(tp._lines)
    assert 's[S_clk]' in code
    assert '== 1' in code


def test_visit_proccall_print():
    x = _make_signal('x', 8, {'reg'})
    tp = _setup_transpiler_with_signals(x)
    tp._lines = []
    node = AHDL_PROCCALL('!hdl_print', (_make_var(x),))
    tp.visit(node)
    code = '\n'.join(tp._lines)
    assert 'printf' in code


def test_visit_proccall_assert():
    x = _make_signal('x', 8, {'reg'})
    tp = _setup_transpiler_with_signals(x)
    tp._lines = []
    node = AHDL_PROCCALL('!hdl_assert', (_make_var(x),))
    tp.visit(node)
    code = '\n'.join(tp._lines)
    assert 'assert' in code.lower() or 'abort' in code.lower()


def test_visit_proccall_unknown_raises():
    tp = AHDLToCTranspiler()
    try:
        tp.visit(AHDL_PROCCALL('!unknown', ()))
        assert False, 'Expected NotImplementedError'
    except NotImplementedError:
        pass


def test_visit_nop():
    tp = AHDLToCTranspiler()
    tp._lines = []
    tp.visit(AHDL_NOP('test'))
    assert all('nop' in l or l.strip().startswith('//') or l.strip() == '' for l in tp._lines)


def test_visit_modulecall_raises():
    tp = AHDLToCTranspiler()
    try:
        tp.visit(AHDL_MODULECALL(None, (), 'inst', 'pfx', ()))
        assert False, 'Expected NotImplementedError'
    except NotImplementedError:
        pass


def test_visit_transition_raises():
    tp = AHDLToCTranspiler()
    try:
        tp.visit(AHDL_TRANSITION('some_state'))
        assert False, 'Expected NotImplementedError'
    except NotImplementedError:
        pass
