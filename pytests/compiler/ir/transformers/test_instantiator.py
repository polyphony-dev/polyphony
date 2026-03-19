from polyphony.compiler.common.env import env
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir.ir import name2var as _v
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.irreader import IrReader as IrParser, ir_stm
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.transformers.instantiator import ModuleInstantiator
from polyphony.compiler.ir.transformers.instantiator import new_find_called_module
from polyphony.compiler.ir.transformers.instantiator import ArgumentApplier
from polyphony.compiler.ir.transformers.instantiator import CallCollector
from polyphony.compiler.ir import ir as new_ir
from polyphony.compiler.ir.transformers.constopt import ConstantOpt
from polyphony.compiler.ir.transformers.typeprop import TypePropagation
from polyphony.compiler.ir.analysis.usedef import UseDefDetector
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.builtin import builtin_symbols
from pytests.compiler.base import setup_test, install_builtins
import pytest


def test_find_called_module():
    setup_test(with_global=False)
    '''
    @module
    class C:
        def __init__(self, size):
            self.a = size
            self.append_worker(self.main)

        def f(self):
            return self.a

        @timed
        def main(self):
            self.a = 1
    '''

    block_src = """
    scope @top
    tags namespace
    var C: class(@top.C)
    var c: object(@top.C)

    blk1:
    mv c (new C 10)

    scope @top.C
    tags module class
    """
    IrParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)
    modules = new_find_called_module([top])
    assert len(modules) == 1
    module, caller, move = modules[0]
    assert caller is top
    assert module is env.scopes['@top.C']
    assert move is top.entry_block.stms[0]
    assert isinstance(move.src, New)


def test_instantiate_no_bind():
    setup_test(with_global=False)
    '''
    @module
    class C:
        def __init__(self, size):
            self.a = size
            self.append_worker(self.main)
            self.append_worker(self.main)

        def f(self):
            return self.a

        @timed
        def main(self):
            self.a = 1
    '''

    block_src = """
    scope @top
    tags namespace
    var C: class(@top.C)
    var c: object(@top.C)

    blk1:
    mv c (new C 10)

    scope @top.C
    tags module class
    var append_worker: function(@top.C.append_worker)
    var __init__: function(@top.C.__init__)
    var f: function(@top.C.f)
    var main: function(@top.C.main)
    var a: int32 { field }

    scope @top.C.append_worker
    tags method lib builtin
    param self: object(@top.C)
    param func: function()
    param loop: bool

    scope @top.C.__init__
    tags ctor method
    param self: object(@top.C)
    param size: int32
    return object(@top.C)

    blk1:
    mv size @in_size
    mv self.a size
    expr (call self.append_worker self.main)
    expr (call self.append_worker self.main)

    scope @top.C.f
    tags method
    param self: object(@top.C)
    return int32

    blk1:
    mv @return self.a
    ret @return

    scope @top.C.main
    tags method worker
    param self: object(@top.C)

    blk1:
    mv self.a 1
    """
    IrParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    C = env.scopes['@top.C']
    modules = new_find_called_module([top])
    names = [''] * len(modules)
    new_modules = ModuleInstantiator().process_modules(modules, names)

    assert len(new_modules) == 1

    C0 = env.scopes['@top.C_0']
    assert new_modules[0] is C0

    blk1 = top.entry_block
    assert len(blk1.stms) == 1
    assert blk1.stms[0] == Move(_v('c'), New(_v('C_0'), [('', Const(10))], {}))
    top_c = top.find_sym('c')
    assert top_c
    assert top_c.typ.is_object()
    assert top_c.typ.scope is C   # type propagation is not done yet

    top_C = top.find_sym('C_0')
    assert top_C
    assert top_C.typ.is_class()
    assert top_C.typ.scope is C0

    assert C0.is_instantiated()
    assert C0.is_class()
    assert C0.parent is top
    C0_a = C0.find_sym('a')
    assert C0_a
    assert C0_a.is_field()
    assert C0_a.scope is C0
    assert C0_a.typ.is_int()

    children_names = [c.name for c in C0.children]
    assert '@top.C_0.__init__' in children_names
    assert '@top.C_0.f' in children_names
    assert '@top.C_0.main_0' in children_names
    assert '@top.C_0.main_1' in children_names
    assert '@top.C_0.main' not in children_names

    i = children_names.index('@top.C_0.__init__')
    C0_ctor = C0.children[i]
    assert C0_ctor.is_ctor()
    assert C0_ctor.is_instantiated()
    assert C0_ctor.parent is C0
    C0_ctor_size = C0_ctor.find_sym('size')
    assert C0_ctor_size.scope is C0_ctor
    assert C0_ctor_size.typ.is_int()
    C0_ctor_self = C0_ctor.find_sym('self')
    assert C0_ctor_self.scope is C0_ctor
    assert C0_ctor_self.typ.is_object()
    assert C0_ctor_self.typ.scope is C0

    # check parameter no binding
    assert C0_ctor.param_names() == ['size']
    blk1 = C0_ctor.entry_block
    assert len(blk1.stms) == 4
    assert blk1.stms[0] == Move(_v('size'), _v('@in_size'))
    assert blk1.stms[1] == Move(_v('self.a'), _v('size'))
    assert blk1.stms[2] == Expr(Call(_v('self.append_worker'), [('', _v('self.main_0'))], {}))
    assert blk1.stms[3] == Expr(Call(_v('self.append_worker'), [('', _v('self.main_1'))], {}))

    # check method instantiation
    i = children_names.index('@top.C_0.f')
    C0_f = C0.children[i]
    assert C0_f.is_method()
    assert C0_f.is_instantiated()
    assert C0_f.parent is C0
    C0_f_self = C0_f.find_sym('self')
    assert C0_f_self.scope is C0_f
    assert C0_f_self.typ.is_object()
    assert C0_f_self.typ.scope is C0

    # check worker instantiation
    i = children_names.index('@top.C_0.main_0')
    C0_main0 = C0.children[i]
    assert C0_main0.is_method()
    assert C0_main0.is_instantiated()
    assert C0_main0.is_worker()
    assert C0_main0.parent is C0
    C0_main0_self = C0_main0.find_sym('self')
    assert C0_main0_self.scope is C0_main0
    assert C0_main0_self.typ.is_object()
    assert C0_main0_self.typ.scope is C0
    main0_sym = C0.find_sym('main_0')
    assert main0_sym
    assert main0_sym.typ.is_function()
    assert main0_sym.typ.scope is C0_main0

    i = children_names.index('@top.C_0.main_1')
    C0_main1 = C0.children[i]
    assert C0_main1.is_method()
    assert C0_main1.is_instantiated()
    assert C0_main1.is_worker()
    assert C0_main1.parent is C0
    C0_main1_self = C0_main1.find_sym('self')
    assert C0_main1_self.scope is C0_main1
    assert C0_main1_self.typ.is_object()
    assert C0_main1_self.typ.scope is C0
    main1_sym = C0.find_sym('main_1')
    assert main1_sym
    assert main1_sym.typ.is_function()
    assert main1_sym.typ.scope is C0_main1

    # check original worker removal
    assert C0.workers == [C0_main0, C0_main1]
    assert C0.find_sym('main') is None


def test_bind_arguments():
    setup_test(with_global=False)
    '''
    @module
    class C:
        def __init__(self, size):
            self.a = size
            self.append_worker(self.main, size)
            self.append_worker(self.main, self.a)
            self.append_worker(self.main, self.a + 1)

        @timed
        def main(self, x):
            self.a = x
    '''

    block_src = """
    scope @top
    tags namespace
    var C: class(@top.C)
    var c: object(@top.C)

    blk1:
    mv c (new C 10)

    scope @top.C
    tags module class
    var append_worker: function(@top.C.append_worker)
    var __init__: function(@top.C.__init__)
    var main: function(@top.C.main)
    var a: int32 { field }

    scope @top.C.append_worker
    tags method lib builtin
    param self: object(@top.C)
    param func: function()
    param loop: bool

    scope @top.C.__init__
    tags ctor method
    param self: object(@top.C)
    param size: int32
    return object(@top.C)

    blk1:
    mv size @in_size
    mv self.a size
    expr (call self.append_worker self.main (+ size size))
    expr (call self.append_worker self.main self.a)
    mv self.a (+ self.a 1)
    expr (call self.append_worker self.main (+ self.a 1))

    scope @top.C.main
    tags method worker
    param self: object(@top.C)
    param x: int32

    blk1:
    mv x @in_x
    mv self.a x
    """
    IrParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    C = env.scopes['@top.C']
    modules = new_find_called_module([top])
    names = [''] * len(modules)
    new_modules = ModuleInstantiator().process_modules(modules, names)

    assert len(new_modules) == 1
    TypePropagation().process_all()
    UseDefDetector().process(top)
    ConstantOpt().process(top)
    for child in new_modules[0].children:
        UseDefDetector().process(child)
        ConstantOpt().process(child)

    C0_ctor = env.scopes['@top.C_0.__init__']
    next_scopes = ArgumentApplier().process_scopes([Scope.global_scope()])
    assert len(next_scopes) == 1
    assert next_scopes[0] is C0_ctor
    assert top.entry_block.stms[0] == Move(_v('c'), New(_v('C_0'), [], {}))

    assert len(C0_ctor.param_names()) == 0
    assert C0_ctor.entry_block.stms[0] == Move(_v('self.a'), Const(10))
    assert C0_ctor.entry_block.stms[1] == Expr(Call(_v('self.append_worker'),
                                                    [('', _v('self.main_0')),
                                                     ('', Const(20))],
                                                    {}))
    assert C0_ctor.entry_block.stms[2] == Expr(Call(_v('self.append_worker'),
                                                    [('', _v('self.main_1')),
                                                     ('', Const(10))],
                                                    {}))
    assert C0_ctor.entry_block.stms[3] == Move(_v('self.a'), Const(11))
    assert C0_ctor.entry_block.stms[4] == Expr(Call(_v('self.append_worker'),
                                                    [('', _v('self.main_2')),
                                                     ('', Const(12))],
                                                    {}))


    next_scopes = ArgumentApplier().process_scopes([C0_ctor])
    assert len(next_scopes) == 0

    C0_main0 = env.scopes['@top.C_0.main_0']
    assert len(C0_main0.param_names()) == 0
    assert C0_main0.entry_block.stms[0] == Move(_v('self.a'), Const(20))

    C0_main1 = env.scopes['@top.C_0.main_1']
    assert len(C0_main1.param_names()) == 0
    assert C0_main1.entry_block.stms[0] == Move(_v('self.a'), Const(10))

    C0_main2 = env.scopes['@top.C_0.main_2']
    assert len(C0_main2.param_names()) == 0
    assert C0_main2.entry_block.stms[0] == Move(_v('self.a'), Const(12))


def test_new_call_collector_imports():
    """Verify CallCollector can be imported."""
    collector = CallCollector()
    assert hasattr(collector, 'calls')
    assert collector.calls == []


def test_new_call_collector_finds_calls():
    """CallCollector should find Call, New, and $new SysCall nodes in stms."""
    setup_test()
    top = Scope.global_scope()

    # Create a callee function
    callee = Scope.create(top, 'callee_func', {'function'}, 0)
    callee.return_type = Type.int()
    callee_blk = Block(callee, nametag='blk1')
    callee.set_entry_block(callee_blk)
    callee.set_exit_block(callee_blk)
    Block.set_order(callee_blk, 0)

    callee_sym = top.add_sym('callee_func', tags=set(), typ=Type.function(callee))

    # Create caller scope with a CALL
    caller = Scope.create(top, 'caller_func', {'function'}, 0)
    caller.add_sym('result', tags=set(), typ=Type.int())
    caller.import_sym(callee_sym)
    caller.return_type = Type.int()
    blk = Block(caller, nametag='blk1')
    caller.set_entry_block(blk)
    caller.set_exit_block(blk)
    call = Call(Temp('callee_func'), args=[], kwargs={})
    blk.append_stm(Move(Temp('result', Ctx.STORE), call))
    Block.set_order(blk, 0)

    # Collect
    results = CallCollector().process(caller)
    assert len(results) == 1
    scope, stm, call_ir = results[0]
    assert scope is caller
    assert isinstance(call_ir, new_ir.Call)


def test_new_call_collector_finds_new():
    """CallCollector should find New nodes."""
    setup_test()
    top = Scope.global_scope()

    # Create a class
    klass = Scope.create(top, 'MyClass', {'class'}, 0)
    ctor = Scope.create(klass, '__init__', {'method', 'ctor'}, 0)
    ctor.add_sym('self', tags={'self'}, typ=Type.object(klass))
    ctor.return_type = Type.object(klass)
    ctor_blk = Block(ctor, nametag='blk1')
    ctor.set_entry_block(ctor_blk)
    ctor.set_exit_block(ctor_blk)
    Block.set_order(ctor_blk, 0)

    klass_sym = top.add_sym('MyClass', tags=set(), typ=Type.klass(klass))

    # Create scope with NEW
    F = Scope.create(top, 'test_func', {'function'}, 0)
    F.add_sym('obj', tags=set(), typ=Type.object(klass))
    F.import_sym(klass_sym)
    F.return_type = Type.none()
    blk = Block(F, nametag='blk1')
    F.set_entry_block(blk)
    F.set_exit_block(blk)
    new_call = New(Temp('MyClass'), args=[], kwargs={})
    blk.append_stm(Move(Temp('obj', Ctx.STORE), new_call))
    Block.set_order(blk, 0)

    results = CallCollector().process(F)
    assert len(results) == 1
    assert isinstance(results[0][2], new_ir.New)


def test_new_module_instantiator_imports():
    """Verify ModuleInstantiator can be imported."""
    inst = ModuleInstantiator()
    assert hasattr(inst, 'process_modules')


def test_new_argument_applier_imports():
    """Verify ArgumentApplier can be imported."""
    applier = ArgumentApplier()
    assert hasattr(applier, 'process_all')
    assert hasattr(applier, 'process_scopes')
    assert hasattr(applier, '_bind_args')
