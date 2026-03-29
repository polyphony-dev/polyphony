"""Tests for Signal class covering uncovered lines."""
from polyphony.compiler.ahdl.signal import Signal
from polyphony.compiler.ahdl.hdlmodule import HDLModule
from polyphony.compiler.ir.irreader import IrReader
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def build_scope():
    setup_test()
    src = '''
scope test
tags function returnable
'''
    parser = IrReader(src)
    parser.parse_scope()
    for name in parser.sources:
        return env.scopes[name]


def make_hdlmodule():
    scope = build_scope()
    hdl = HDLModule(scope, scope.base_name, scope.base_name)
    env.append_hdlscope(hdl)
    return hdl


def test_signal_eq():
    hdl = make_hdlmodule()
    sig1 = hdl.gen_sig('foo', 8, {'reg'})
    sig2 = hdl.gen_sig('bar', 8, {'reg'})
    # same name -> equal
    sig3 = hdl.gen_sig('foo', 4, {'net'})
    assert sig1 == sig3
    assert sig1 != sig2


def test_signal_lt():
    hdl = make_hdlmodule()
    sig_a = hdl.gen_sig('aaa', 8, {'reg'})
    sig_b = hdl.gen_sig('bbb', 8, {'reg'})
    assert sig_a < sig_b
    assert not sig_b < sig_a


def test_signal_repr():
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('myreg', 8, {'reg'})
    r = repr(sig)
    assert 'myreg' in r
    assert '8' in r


def test_signal_str():
    hdl = make_hdlmodule()
    sig = hdl.gen_sig('mysig', 16, {'reg'})
    s = str(sig)
    assert 'mysig' in s
    assert '16' in s
