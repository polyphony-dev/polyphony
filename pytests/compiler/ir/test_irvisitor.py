"""Tests for new IrVisitor and IrTransformer."""
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir import ir as new
from polyphony.compiler.ir.irvisitor import IrVisitor, IrTransformer
from polyphony.compiler.ir.irreader import IRReader as IRParser
from polyphony.compiler.ir.irwriter import IRWriter
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test, make_block, MockScope


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
    """Doubles all integer constants (functional — returns new node)."""
    def visit_Const(self, ir):
        if isinstance(ir.value, int) and not isinstance(ir.value, bool):
            return ir.model_copy(update={'value': ir.value * 2})
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
    """Renames all Temp variables by adding a suffix (functional — returns new node)."""
    def __init__(self, suffix):
        super().__init__()
        self.suffix = suffix

    def visit_Temp(self, ir):
        return ir.model_copy(update={'name': ir.name + self.suffix})


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
        object.__setattr__(ir, 'src', self.visit(ir.src))
        object.__setattr__(ir, 'dst', self.visit(ir.dst))
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
    from polyphony.compiler.ir.ir import Const as OLD_CONST
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
    assert isinstance(stm, Move)
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


# ============================================================
# IrVisitor -- coverage tests (uncovered lines)
# ============================================================

class CollectingVisitor(IrVisitor):
    """Records class names of all visited nodes."""
    def __init__(self):
        super().__init__()
        self.visited = []

    def visit(self, ir):
        self.visited.append(ir.__class__.__name__)
        return super().visit(ir)


def test_visitor_path_exp():
    """Line 29: block.path_exp branch in _process_block."""
    src = '''
scope F
tags function
var x: int32

blk1:
mv x 1
'''
    scope = build_scope(src)
    blk = scope.entry_block
    blk.path_exp = Const(value=42)

    v = CollectingVisitor()
    v.process(scope)
    assert 'Const' in v.visited


def test_visitor_visit_returns_none():
    """Line 38: visit returns None when visitor method returns None."""
    v = IrVisitor()
    result = v.visit(Const(value=1))
    assert result is None


def test_visitor_unop():
    """Line 43: visit_UnOp via direct IR construction."""
    v = CollectingVisitor()
    ir = UnOp(op='USub', exp=Const(value=5))
    v.visit(ir)
    assert 'UnOp' in v.visited
    assert 'Const' in v.visited


def test_visitor_condop():
    """Lines 54-56: visit_CondOp."""
    v = CollectingVisitor()
    ir = CondOp(
        cond=Const(value=True),
        left=Const(value=1),
        right=Const(value=2),
    )
    v.visit(ir)
    assert 'CondOp' in v.visited
    assert v.visited.count('Const') == 3


def test_visitor_polyop():
    """Lines 59-60: visit_PolyOp."""
    v = CollectingVisitor()
    ir = PolyOp(op='Add', values=[Const(value=1), Const(value=2), Const(value=3)])
    v.visit(ir)
    assert 'PolyOp' in v.visited
    assert v.visited.count('Const') == 3


def test_visitor_kwargs():
    """Line 66: _visit_args kwargs branch."""
    v = CollectingVisitor()
    func = Temp(name='f', ctx=Ctx.LOAD)
    ir = Call(
        func=func,
        args=[('a', Const(value=1))],
        kwargs={'key': Const(value=99)},
    )
    v.visit(ir)
    const_count = v.visited.count('Const')
    assert const_count >= 2  # arg + kwarg


def test_visitor_array_with_repeat():
    """Lines 99->101: Array with non-None repeat."""
    v = CollectingVisitor()
    ir = Array(items=[Const(value=1), Const(value=2)], repeat=Const(value=3))
    v.visit(ir)
    assert 'Array' in v.visited
    assert v.visited.count('Const') == 3  # repeat + 2 items


def test_visitor_phi_with_none_args():
    """Lines 137->136, 140->139: Phi with None args and ps."""
    v = CollectingVisitor()
    phi = Phi(
        var=Temp(name='x', ctx=Ctx.STORE),
        args=[Const(value=1), None, Const(value=2)],
        ps=[Const(value=True), None, Const(value=False)],
    )
    v.visit(phi)
    assert 'Phi' in v.visited


def test_visitor_uphi():
    """Line 144: visit_UPhi."""
    v = CollectingVisitor()
    uphi = UPhi(
        var=Temp(name='x', ctx=Ctx.STORE),
        args=[Const(value=1)],
    )
    v.visit(uphi)
    assert 'UPhi' in v.visited


def test_visitor_mstm():
    """Lines 150-151: visit_MStm."""
    v = CollectingVisitor()
    inner_move = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=Const(value=1))
    mstm = MStm(stms=[inner_move])
    v.visit(mstm)
    assert 'MStm' in v.visited
    assert 'Move' in v.visited


# ============================================================
# IrTransformer -- coverage tests (model_copy branches)
# ============================================================

class ConstReplacer(IrTransformer):
    """Replaces all Const(value=0) with Const(value=999) to trigger model_copy."""
    def visit_Const(self, ir):
        if isinstance(ir.value, int) and ir.value == 0:
            return Const(value=999)
        return ir


def test_transformer_unop_changed():
    """Lines 184-187: IrTransformer.visit_UnOp model_copy branch."""
    replacer = ConstReplacer()
    replacer.new_stms = []
    ir = UnOp(op='USub', exp=Const(value=0))
    result = replacer.visit(ir)
    assert isinstance(result, UnOp)
    assert result.exp.value == 999
    assert result is not ir


def test_transformer_unop_unchanged():
    """Lines 184-187: UnOp unchanged path."""
    t = IrTransformer()
    t.new_stms = []
    ir = UnOp(op='USub', exp=Const(value=5))
    result = t.visit(ir)
    assert result is ir


def test_transformer_relop_changed():
    """Lines 197-201: IrTransformer.visit_RelOp model_copy branch."""
    src = '''
scope F
tags function
var x: bool

blk1:
mv x (== 0 1)
'''
    scope = build_scope(src)
    ConstReplacer().process(scope)
    stm = scope.entry_block.stms[0]
    assert isinstance(stm.src, RelOp)
    assert stm.src.left.value == 999


def test_transformer_condop_changed():
    """Lines 204-209: IrTransformer.visit_CondOp model_copy branch."""
    replacer = ConstReplacer()
    replacer.new_stms = []
    ir = CondOp(cond=Const(value=0), left=Const(value=1), right=Const(value=2))
    result = replacer.visit(ir)
    assert isinstance(result, CondOp)
    assert result.cond.value == 999
    assert result is not ir


def test_transformer_condop_unchanged():
    """Lines 204-209: CondOp unchanged path."""
    t = IrTransformer()
    t.new_stms = []
    ir = CondOp(cond=Const(value=1), left=Const(value=2), right=Const(value=3))
    result = t.visit(ir)
    assert result is ir


def test_transformer_polyop_changed():
    """Lines 212-215: IrTransformer.visit_PolyOp model_copy branch."""
    replacer = ConstReplacer()
    replacer.new_stms = []
    ir = PolyOp(op='Add', values=[Const(value=0), Const(value=1)])
    result = replacer.visit(ir)
    assert isinstance(result, PolyOp)
    assert result.values[0].value == 999
    assert result is not ir


def test_transformer_polyop_unchanged():
    """Lines 212-215: PolyOp unchanged path."""
    t = IrTransformer()
    t.new_stms = []
    ir = PolyOp(op='Add', values=[Const(value=1), Const(value=2)])
    result = t.visit(ir)
    assert result is ir


def test_transformer_call_changed():
    """Line 226: IrTransformer.visit_Call model_copy branch."""
    src = '''
scope F
tags function
var f: function(F)
var r: int32

blk1:
mv r (call f 0)
'''
    scope = build_scope(src)
    ConstReplacer().process(scope)
    stm = scope.entry_block.stms[0]
    assert isinstance(stm.src, Call)
    assert stm.src.args[0][1].value == 999


def test_transformer_syscall_changed():
    """Lines 230-234: IrTransformer.visit_SysCall model_copy branch."""
    replacer = ConstReplacer()
    replacer.new_stms = []
    func = Temp(name='sys_f', ctx=Ctx.CALL)
    ir = SysCall(func=func, args=[('a', Const(value=0))])
    result = replacer.visit(ir)
    assert isinstance(result, SysCall)
    assert result.args[0][1].value == 999
    assert result is not ir


def test_transformer_syscall_unchanged():
    """Lines 230-234: SysCall unchanged path."""
    t = IrTransformer()
    t.new_stms = []
    func = Temp(name='sys_f', ctx=Ctx.CALL)
    ir = SysCall(func=func, args=[('a', Const(value=1))])
    result = t.visit(ir)
    assert result is ir


def test_transformer_new_changed():
    """Lines 237-241: IrTransformer.visit_New model_copy branch."""
    replacer = ConstReplacer()
    replacer.new_stms = []
    func = Temp(name='Cls', ctx=Ctx.CALL)
    ir = New(func=func, args=[('a', Const(value=0))])
    result = replacer.visit(ir)
    assert isinstance(result, New)
    assert result.args[0][1].value == 999
    assert result is not ir


def test_transformer_new_unchanged():
    """Lines 237-241: New unchanged path."""
    t = IrTransformer()
    t.new_stms = []
    func = Temp(name='Cls', ctx=Ctx.CALL)
    ir = New(func=func, args=[('a', Const(value=1))])
    result = t.visit(ir)
    assert result is ir


def test_transformer_attr_changed():
    """Lines 250-253: IrTransformer.visit_Attr model_copy branch."""
    class TempReplacer(IrTransformer):
        def visit_Temp(self, ir):
            if ir.name == 'old':
                return ir.model_copy(update={'name': 'new'})
            return ir

    t = TempReplacer()
    t.new_stms = []
    ir = Attr(exp=Temp(name='old'), attr='field', ctx=Ctx.LOAD)
    result = t.visit(ir)
    assert isinstance(result, Attr)
    assert result.exp.name == 'new'
    assert result is not ir


def test_transformer_mref_changed():
    """Line 259: IrTransformer.visit_MRef model_copy (offset changed)."""
    src = '''
scope F
tags function
var xs: list<int32>[10]
var v: int32

blk1:
mv v (mld xs 0)
'''
    scope = build_scope(src)
    ConstReplacer().process(scope)
    stm = scope.entry_block.stms[0]
    assert isinstance(stm.src, MRef)
    assert stm.src.offset.value == 999


def test_transformer_mstore_changed():
    """Line 267: IrTransformer.visit_MStore model_copy (exp changed)."""
    src = '''
scope F
tags function
var xs: list<int32>[10]

blk1:
expr (mst xs 1 0)
'''
    scope = build_scope(src)
    ConstReplacer().process(scope)
    stm = scope.entry_block.stms[0]
    assert isinstance(stm.exp, MStore)
    assert stm.exp.exp.value == 999


def test_transformer_array_changed():
    """Lines 271-277: IrTransformer.visit_Array model_copy (items changed)."""
    replacer = ConstReplacer()
    replacer.new_stms = []
    ir = Array(items=[Const(value=0), Const(value=1)], repeat=Const(value=1))
    result = replacer.visit(ir)
    assert isinstance(result, Array)
    assert result.items[0].value == 999
    assert result is not ir


def test_transformer_array_unchanged():
    """Lines 271-277: Array unchanged path."""
    t = IrTransformer()
    t.new_stms = []
    ir = Array(items=[Const(value=1), Const(value=2)], repeat=Const(value=1))
    result = t.visit(ir)
    assert result is ir


def test_transformer_array_repeat_changed():
    """Lines 271-277: Array repeat changed."""
    replacer = ConstReplacer()
    replacer.new_stms = []
    ir = Array(items=[Const(value=1)], repeat=Const(value=0))
    result = replacer.visit(ir)
    assert isinstance(result, Array)
    assert result.repeat.value == 999


def test_transformer_cexpr():
    """Lines 286-287: IrTransformer.visit_CExpr via direct IR construction."""
    t = IrTransformer()
    t.new_stms = []
    cexpr = CExpr(
        cond=Const(value=True),
        exp=Const(value=42),
    )
    t.visit(cexpr)
    assert len(t.new_stms) == 1
    assert isinstance(t.new_stms[0], CExpr)


def test_transformer_cexpr_with_replacement():
    """Lines 286-287: CExpr cond replaced by transformer."""
    replacer = ConstReplacer()
    replacer.new_stms = []
    cexpr = CExpr(
        cond=Const(value=0),
        exp=Const(value=42),
    )
    replacer.visit(cexpr)
    assert len(replacer.new_stms) == 1
    assert replacer.new_stms[0].cond.value == 999


def test_transformer_cmove():
    """Lines 295-296: IrTransformer.visit_CMove via direct IR construction."""
    replacer = ConstReplacer()
    replacer.new_stms = []
    cmove = CMove(
        cond=Const(value=0),
        dst=Temp(name='x', ctx=Ctx.STORE),
        src=Const(value=5),
    )
    replacer.visit(cmove)
    assert len(replacer.new_stms) == 1
    assert isinstance(replacer.new_stms[0], CMove)
    assert replacer.new_stms[0].cond.value == 999


def test_transformer_cjump():
    """Lines 299-300: IrTransformer.visit_CJump."""
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
    IrTransformer().process(scope)
    blk = scope.entry_block
    assert any(isinstance(s, CJump) for s in blk.stms)


def test_transformer_mcjump():
    """Lines 303-305: IrTransformer.visit_MCJump via direct IR construction."""
    t = IrTransformer()
    t.new_stms = []
    blk1 = make_block()
    blk2 = make_block()
    mcjump = MCJump(
        conds=[Const(value=True), Const(value=False)],
        targets=[blk1, blk2],
    )
    t.visit(mcjump)
    assert len(t.new_stms) == 1
    assert isinstance(t.new_stms[0], MCJump)


def test_transformer_mcjump_with_replacement():
    """Lines 303-305: MCJump conds replaced by transformer."""
    replacer = ConstReplacer()
    replacer.new_stms = []
    blk1 = make_block()
    blk2 = make_block()
    mcjump = MCJump(
        conds=[Const(value=0), Const(value=1)],
        targets=[blk1, blk2],
    )
    replacer.visit(mcjump)
    assert len(replacer.new_stms) == 1
    assert replacer.new_stms[0].conds[0].value == 999


def test_transformer_phi():
    """Lines 315-323: IrTransformer.visit_Phi via direct IR construction."""
    t = IrTransformer()
    t.new_stms = []
    phi = Phi(
        var=Temp(name='x', ctx=Ctx.STORE),
        args=[Const(value=1), Const(value=2)],
    )
    t.visit(phi)
    assert len(t.new_stms) == 1
    assert isinstance(t.new_stms[0], Phi)


def test_transformer_phi_with_ps():
    """Lines 319-322: Phi with ps list in transformer."""
    t = IrTransformer()
    t.new_stms = []
    phi = Phi(
        var=Temp(name='x', ctx=Ctx.STORE),
        args=[Const(value=1), None, Const(value=2)],
        ps=[Const(value=True), None, Const(value=False)],
    )
    t.visit(phi)
    assert len(t.new_stms) == 1
    assert isinstance(t.new_stms[0], Phi)


def test_transformer_phi_with_none_args():
    """Lines 316-318: Phi with None in args list."""
    t = IrTransformer()
    t.new_stms = []
    phi = Phi(
        var=Temp(name='x', ctx=Ctx.STORE),
        args=[Const(value=1), None],
    )
    t.visit(phi)
    assert len(t.new_stms) == 1


def test_transformer_uphi():
    """Line 326: IrTransformer.visit_UPhi."""
    t = IrTransformer()
    t.new_stms = []
    uphi = UPhi(
        var=Temp(name='x', ctx=Ctx.STORE),
        args=[Const(value=1)],
    )
    t.visit(uphi)
    assert len(t.new_stms) == 1
    assert isinstance(t.new_stms[0], UPhi)


def test_transformer_lphi():
    """Line 329: IrTransformer.visit_LPhi."""
    t = IrTransformer()
    t.new_stms = []
    lphi = LPhi(
        var=Temp(name='x', ctx=Ctx.STORE),
        args=[Const(value=1)],
    )
    t.visit(lphi)
    assert len(t.new_stms) == 1
    assert isinstance(t.new_stms[0], LPhi)


def test_transformer_mstm():
    """Lines 332-338: IrTransformer.visit_MStm."""
    t = IrTransformer()
    t.new_stms = []
    inner_move = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=Const(value=1))
    mstm = MStm(stms=[inner_move])
    t.visit(mstm)
    assert len(t.new_stms) == 1
    assert isinstance(t.new_stms[0], MStm)


def test_transformer_mstm_with_multiple_stms():
    """Lines 332-338: MStm with multiple inner statements."""
    t = IrTransformer()
    t.new_stms = []
    m1 = Move(dst=Temp(name='x', ctx=Ctx.STORE), src=Const(value=1))
    m2 = Move(dst=Temp(name='y', ctx=Ctx.STORE), src=Const(value=2))
    mstm = MStm(stms=[m1, m2])
    t.visit(mstm)
    assert len(t.new_stms) == 1
    assert isinstance(t.new_stms[0], MStm)


def test_transformer_block_with_jump_at_end():
    """Line 174-175: _process_block with Jump at end of stms."""
    src = '''
scope F
tags function returnable
return int32
var x: int32

blk1:
mv x 1
j exit

exit:
ret @return
'''
    scope = build_scope(src)
    IrTransformer().process(scope)
    blk = scope.entry_block
    assert isinstance(blk.stms[-1], Jump)


def test_visitor_lphi():
    """Line 146-147: visit_LPhi in IrVisitor."""
    v = CollectingVisitor()
    lphi = LPhi(
        var=Temp(name='x', ctx=Ctx.STORE),
        args=[Const(value=1)],
    )
    v.visit(lphi)
    assert 'LPhi' in v.visited
