"""Tests for new IrVisitor and IrTransformer."""
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir import ir as new
from polyphony.compiler.ir.ir_visitor import IrVisitor, IrTransformer
from polyphony.compiler.ir.irreader import IRReader as IRParser
from polyphony.compiler.ir.irwriter import IRWriter
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def build_scope(src):
    setup_test()
    parser = IRParser(src)
    parser.parse_scope()
    for name in parser.sources:
        return env.scopes[name]


# ============================================================
# IrVisitor tests
# ============================================================

class NodeCounter(IrVisitor):
    """Counts visits to each node type."""
    def __init__(self):
        super().__init__()
        self.counts = {}

    def visit(self, ir):
        name = ir.__class__.__name__
        self.counts[name] = self.counts.get(name, 0) + 1
        return super().visit(ir)


def test_visitor_counts_nodes():
    src = '''
scope F
tags function
var x: int32
var y: int32
var z: int32

blk1:
mv x 1
mv y 2
mv z (+ x y)
'''
    scope = build_scope(src)

    counter = NodeCounter()
    counter.process(scope)

    assert counter.counts['Move'] == 3
    assert counter.counts['Const'] == 2  # 1, 2
    assert counter.counts['Temp'] >= 5   # x(store), 1, y(store), 2, z(store), x(load), y(load)
    assert counter.counts['BinOp'] == 1


class UseCollector(IrVisitor):
    """Collects all Temp names in LOAD context."""
    def __init__(self):
        super().__init__()
        self.used_names = set()

    def visit_Temp(self, ir):
        if ir.ctx == new.Ctx.LOAD:
            self.used_names.add(ir.name)


def test_visitor_collect_uses():
    src = '''
scope F
tags function
var a: int32
var b: int32
var c: int32

blk1:
mv a 1
mv b 2
mv c (+ a b)
'''
    scope = build_scope(src)

    collector = UseCollector()
    collector.process(scope)

    assert 'a' in collector.used_names
    assert 'b' in collector.used_names
    assert 'c' not in collector.used_names  # only defined, never used


def test_visitor_multi_block():
    src = '''
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
ret @return
'''
    scope = build_scope(src)

    counter = NodeCounter()
    counter.process(scope)

    assert counter.counts['Move'] >= 3
    assert counter.counts['CJump'] == 1
    assert counter.counts['Jump'] == 2
    assert counter.counts['Ret'] == 1


# ============================================================
# IrTransformer tests
# ============================================================

class ConstDoubler(IrTransformer):
    """Doubles all integer constants."""
    def visit_Const(self, ir):
        if isinstance(ir.value, int) and not isinstance(ir.value, bool):
            ir.value = ir.value * 2
        return ir


def test_transformer_doubles_consts():
    src = '''
scope F
tags function
var x: int32
var y: int32

blk1:
mv x 5
mv y (+ x 10)
'''
    scope = build_scope(src)

    ConstDoubler().process(scope)

    blk = scope.entry_block
    # mv x 5 -> mv x 10
    stm0 = blk.stms[0]
    assert isinstance(stm0, new.Move)
    assert stm0.src.value == 10
    # mv y (+ x 10) -> mv y (+ x 20)
    stm1 = blk.stms[1]
    assert isinstance(stm1, new.Move)
    assert isinstance(stm1.src, new.BinOp)
    assert stm1.src.right.value == 20


class VarRenamer(IrTransformer):
    """Renames all Temp variables by adding a suffix."""
    def __init__(self, suffix):
        super().__init__()
        self.suffix = suffix

    def visit_Temp(self, ir):
        ir.name = ir.name + self.suffix
        return ir


def test_transformer_renames_vars():
    src = '''
scope F
tags function
var x: int32
var y: int32

blk1:
mv x 1
mv y x
'''
    scope = build_scope(src)
    # Add suffixed syms so scope lookup works
    scope.add_sym('x_v2', tags=set(), typ=Type.int(32))
    scope.add_sym('y_v2', tags=set(), typ=Type.int(32))


    VarRenamer('_v2').process(scope)

    blk = scope.entry_block
    stm0 = blk.stms[0]
    assert stm0.dst.name == 'x_v2'
    stm1 = blk.stms[1]
    assert stm1.dst.name == 'y_v2'
    assert stm1.src.name == 'x_v2'


class StmInserter(IrTransformer):
    """Inserts a NOP (mv _nop 0) before each Move statement."""
    def visit_Move(self, ir):
        nop = new.Move(
            dst=new.Temp(name='_nop', ctx=new.Ctx.STORE),
            src=new.Const(value=0),
        )
        self.new_stms.append(nop)
        ir.src = self.visit(ir.src)
        ir.dst = self.visit(ir.dst)
        self.new_stms.append(ir)


def test_transformer_inserts_stms():
    src = '''
scope F
tags function
var x: int32
var _nop: int32

blk1:
mv x 1
'''
    scope = build_scope(src)

    StmInserter().process(scope)

    blk = scope.entry_block
    assert len(blk.stms) == 2
    assert blk.stms[0].dst.name == '_nop'
    assert blk.stms[1].dst.name == 'x'


def test_transformer_block_refs():
    """After transform, stm.block must point to the correct block."""
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 1
'''
    scope = build_scope(src)

    ConstDoubler().process(scope)

    for blk in scope.traverse_blocks():
        for stm in blk.stms:
            assert stm.block is blk


class IdentityTransformer(IrTransformer):
    """Does nothing — verifies the base transformer preserves everything."""
    pass


def test_identity_transformer():
    src = '''
scope F
tags function
var x: int32
var y: int32

blk1:
mv x 1
mv y (+ x 2)
'''
    scope = build_scope(src)
    writer = IRWriter()
    before = [writer.write_stm(s) for s in scope.entry_block.stms]


    IdentityTransformer().process(scope)


    after = [writer.write_stm(s) for s in scope.entry_block.stms]
    assert before == after


def test_transformer_preserves_path_exp():
    """IrTransformer must not touch block.path_exp (it's old IR).
    path_exp should remain intact after transformation."""
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 1
'''
    scope = build_scope(src)
    blk = scope.entry_block
    # Simulate path_exp set by a prior pass (old IR)
    from polyphony.compiler.ir.ir import CONST as OLD_CONST
    blk.path_exp = OLD_CONST(1)

    IdentityTransformer().process(scope)

    # path_exp must still be the old CONST, not None or new Const
    assert blk.path_exp is not None
    assert isinstance(blk.path_exp, OLD_CONST)
    assert blk.path_exp.value == 1


def test_transformer_via_wrapper():
    """IrTransformer subclass used through a wrapper class."""
    class AdaptedConstDoubler:
        def process(self, scope):
            ConstDoubler().process(scope)

    src = '''
scope F
tags function
var x: int32

blk1:
mv x 5
'''
    scope = build_scope(src)
    AdaptedConstDoubler().process(scope)

    stm = scope.entry_block.stms[0]
    assert isinstance(stm, (MOVE, new.Move))
    assert stm.src.value == 10


def test_transformer_with_call():
    """Transformer correctly traverses Call arguments."""
    src = '''
scope F
tags function
var f: function(F)
var r: int32

blk1:
mv r (call f 3)
'''
    scope = build_scope(src)

    ConstDoubler().process(scope)

    stm = scope.entry_block.stms[0]
    assert isinstance(stm.src, new.Call)
    assert stm.src.args[0][1].value == 6  # 3 * 2


def test_transformer_with_mref_mstore():
    """Transformer traverses MRef and MStore children."""
    src = '''
scope F
tags function
var xs: list<int32>[10]
var v: int32

blk1:
mv v (mld xs 3)
expr (mst xs 0 7)
'''
    scope = build_scope(src)

    ConstDoubler().process(scope)

    blk = scope.entry_block
    # mld offset 3 -> 6
    stm0 = blk.stms[0]
    assert stm0.src.offset.value == 6
    # mst value 7 -> 14
    stm1 = blk.stms[1]
    assert stm1.exp.exp.value == 14
