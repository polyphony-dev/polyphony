from polyphony.compiler.common.env import env
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir.ir import name2var as _v
from polyphony.compiler.ir.irreader import IrReader
from polyphony.compiler.ir.transformers.inlineopt import FlattenModule
from polyphony.compiler.ir.builtin import builtin_symbols
from pytests.compiler.base import setup_test, setup_libs, install_builtins
import pytest


def test_flatten_worker():
    setup_test(with_global=False)
    src = """
    scope @top
    tags namespace
    var M: class(@top.M)
    var N: class(@top.N)

    blk1:
    mv m (new M)

    scope @top.M
    tags module class instantiated
    var append_worker: function(@top.M.append_worker)
    var n: object(@top.N)

    scope @top.M.__init__
    tags ctor method instantiated
    param self: object(@top.M)

    blk1:
    mv self.n (syscall $new N)
    mv self.n.x 10
    expr (call self.n.append_worker self.n.main)

    scope @top.M.append_worker
    tags method lib builtin instantiated
    param self: object(@top.M)
    param func: function()
    param loop: bool

    scope @top.N
    tags module class instantiated
    var append_worker: function(@top.N.append_worker)
    var main: function(@top.N.main)
    var x: int32

    scope @top.N.append_worker
    tags method lib builtin instantiated
    param self: object(@top.N)
    param func: function()
    param loop: bool

    scope @top.N.main
    tags method instantiated
    param self: object(@top.N)
    param x: int32

    blk1:
    mv self.x x
    """
    IrReader(src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    m_ctor = env.scopes['@top.M.__init__']
    scopes = FlattenModule().process(m_ctor)

    blk = m_ctor.entry_block
    assert len(blk.stms) == 3
    assert blk.stms[0] == Move(_v('self.n'), SysCall(_v('$new'), [('', _v('N'))], {}))
    assert blk.stms[1] == Move(_v('self.n.x'), Const(10))
    assert blk.stms[2] == Expr(Call(_v('self.append_worker'), [('', _v('self.n_main'))], {}))

    assert len(scopes) == 1
    n_main = scopes[0]
    assert n_main.name == '@top.M.n_main'
    blk = n_main.entry_block
    assert len(blk.stms) == 1
    assert blk.stms[0] == Move(_v('self.n.x'), _v('x'))


def test_flatten_assign_method():
    setup_test()
    setup_libs('io')
    src = """
    scope @top.M
    tags module class instantiated
    var n: object(@top.N)

    scope @top.M.__init__
    tags ctor method instantiated
    param self: object(@top.M)

    blk1:
    mv self.n (syscall $new N)
    expr (call self.n.q.assign self.n.func)

    scope @top.N
    tags module class instantiated
    var func: function(@top.N.func)
    var q: object(polyphony.io.Port)
    var addr: int32
    var mem: list<int32>[8]

    scope @top.N.func
    tags method instantiated assigned closure
    param self: object(@top.N)
    return int32

    blk1:
    mv @return (mld self.mem self.addr)
    ret @return
    """

    IrReader(src).parse_scope()
    top = env.scopes['@top']
    from polyphony.compiler.ir.types.type import Type
    top.add_sym('M', tags=set(), typ=Type.klass('@top.M'))
    top.add_sym('N', tags=set(), typ=Type.klass('@top.N'))
    install_builtins(top)

    m_ctor = env.scopes['@top.M.__init__']
    scopes = FlattenModule().process(m_ctor)

    blk = m_ctor.entry_block
    assert len(blk.stms) == 2
    assert blk.stms[0] == Move(_v('self.n'), SysCall(_v('$new'), [('', _v('N'))], {}))
    assert blk.stms[1] == Expr(Call(_v('self.n.q.assign'), [('', _v('self.n_func'))], {}))

    assert len(scopes) == 1
    n_main = scopes[0]
    assert n_main.name == '@top.M.n_func'
    blk = n_main.entry_block
    assert len(blk.stms) == 2
    assert blk.stms[0] == Move(_v('@return'), MRef(_v('self.n.mem'), _v('self.n.addr')))
    assert blk.stms[1] == Ret(_v('@return'))
