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
