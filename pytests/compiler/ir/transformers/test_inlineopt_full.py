"""Tests for InlineOpt and FlattenModule."""
from polyphony.compiler.ir.ir import Ctx as OldCtx, Const, Temp, Attr, New, Move, Expr, Call, Ret, Jump
from polyphony.compiler.ir import ir as new_ir
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.transformers.inlineopt import (
    InlineOpt, FlattenModule,
)
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def test_new_inline_opt_imports():
    """Verify InlineOpt can be imported and has process_scopes."""
    opt = InlineOpt()
    assert hasattr(opt, 'process_scopes')


def test_new_flatten_module_imports():
    """Verify FlattenModule can be imported."""
    fm = FlattenModule()
    assert hasattr(fm, 'process')


def test_new_flatten_module_no_parent():
    """FlattenModule should return empty list for non-module scopes."""
    setup_test()
    top = Scope.global_scope()

    # Create a function scope (not in a module)
    F = Scope.create(top, 'test_func', {'function'}, 0)
    F.return_type = Type.int()
    blk = Block(F, nametag='blk1')
    F.set_entry_block(blk)
    F.set_exit_block(blk)
    blk.append_stm(Move(Temp('x', OldCtx.STORE), Const(0)))
    Block.set_order(blk, 0)

    scopes = FlattenModule().process(F)
    assert scopes == [] or scopes is None or len(scopes) == 0


def test_call_collector():
    """CallCollector should collect Call nodes from block.stms."""
    from collections import defaultdict
    from polyphony.compiler.ir.transformers.inlineopt import CallCollector

    setup_test()
    top = Scope.global_scope()

    # Create callee
    callee = Scope.create(top, 'g', {'function', 'returnable'}, 0)
    callee.return_type = Type.int()
    callee_blk = Block(callee, nametag='blk1')
    callee.set_entry_block(callee_blk)
    callee.set_exit_block(callee_blk)
    callee_blk.append_stm(Ret(Const(0)))
    Block.set_order(callee_blk, 0)
    top.add_sym('g', tags=set(), typ=Type.function(callee, Type.int(), ()))

    # Create caller that calls g
    caller = Scope.create(top, 'f', {'function'}, 0)
    caller.return_type = Type.none()
    caller.import_sym(top.find_sym('g'))
    caller_blk = Block(caller, nametag='blk1')
    caller.set_entry_block(caller_blk)
    caller.set_exit_block(caller_blk)
    call = Call(Temp('g'), args=[], kwargs={})
    caller_blk.append_stm(Move(Temp('result', OldCtx.STORE), call))
    caller.add_sym('result', tags=set(), typ=Type.int())
    Block.set_order(caller_blk, 0)

    calls = defaultdict(list)
    collector = CallCollector(calls)
    collector.process(caller)

    assert len(calls) == 1
    assert callee in calls
    assert len(calls[callee]) == 1


def test_all_variable_collector():
    """AllVariableCollector should collect all named variables with symbols."""
    from polyphony.compiler.ir.transformers.inlineopt import AllVariableCollector

    setup_test()
    top = Scope.global_scope()
    F = Scope.create(top, 'f', {'function'}, 0)
    F.add_sym('x', tags=set(), typ=Type.int())
    F.add_sym('y', tags=set(), typ=Type.int())
    F.return_type = Type.none()
    blk = Block(F, nametag='blk1')
    F.set_entry_block(blk)
    F.set_exit_block(blk)
    blk.append_stm(Move(Temp('x', OldCtx.STORE), Const(1)))
    blk.append_stm(Move(Temp('y', OldCtx.STORE), Temp('x')))
    Block.set_order(blk, 0)

    result = AllVariableCollector().process(F)
    names = [v.name for v in result]
    assert 'x' in names
    assert 'y' in names


def test_nonlocal_variable_collector():
    """NonlocalVariableCollector should collect variables defined outside scope."""
    from polyphony.compiler.ir.transformers.inlineopt import NonlocalVariableCollector

    setup_test()
    top = Scope.global_scope()
    outer = Scope.create(top, 'outer', {'function'}, 0)
    outer_sym = outer.add_sym('a', tags=set(), typ=Type.int())
    inner = Scope.create(outer, 'inner', {'function'}, 0)
    inner.import_sym(outer_sym)
    inner.add_sym('b', tags=set(), typ=Type.int())
    inner.return_type = Type.none()
    blk = Block(inner, nametag='blk1')
    inner.set_entry_block(blk)
    inner.set_exit_block(blk)
    blk.append_stm(Move(Temp('b', OldCtx.STORE), Temp('a')))
    Block.set_order(blk, 0)

    result = NonlocalVariableCollector().process(inner)
    names = [v.name for v in result]
    assert 'a' in names
    assert 'b' not in names


def test_local_variable_collector():
    """LocalVariableCollector should collect variables defined in the current scope."""
    from polyphony.compiler.ir.transformers.inlineopt import LocalVariableCollector

    setup_test()
    top = Scope.global_scope()
    outer = Scope.create(top, 'outer', {'function'}, 0)
    outer_sym = outer.add_sym('a', tags=set(), typ=Type.int())
    inner = Scope.create(outer, 'inner', {'function'}, 0)
    inner.import_sym(outer_sym)
    inner.add_sym('b', tags=set(), typ=Type.int())
    inner.return_type = Type.none()
    blk = Block(inner, nametag='blk1')
    inner.set_entry_block(blk)
    inner.set_exit_block(blk)
    blk.append_stm(Move(Temp('b', OldCtx.STORE), Temp('a')))
    Block.set_order(blk, 0)

    result = LocalVariableCollector().process(inner)
    names = [v.name for v in result]
    assert 'b' in names
    assert 'a' not in names


def test_ir_replacer():
    """IRReplacer should replace variables based on symbol map."""
    from polyphony.compiler.ir.transformers.inlineopt import IRReplacer

    setup_test()
    top = Scope.global_scope()
    F = Scope.create(top, 'f', {'function'}, 0)
    x_sym = F.add_sym('x', tags=set(), typ=Type.int())
    F.add_sym('y', tags=set(), typ=Type.int())
    F.return_type = Type.none()
    blk = Block(F, nametag='blk1')
    F.set_entry_block(blk)
    F.set_exit_block(blk)
    blk.append_stm(Move(Temp('y', OldCtx.STORE), Temp('x')))
    Block.set_order(blk, 0)

    replace_map = {x_sym: Const(value=42)}
    IRReplacer(replace_map).process(F, F.entry_block)

    mv = blk.stms[0]
    assert isinstance(mv.src, Const)
    assert mv.src.value == 42


def test_stms_visitor_visitor_methods():
    """_StmsVisitor visit methods should handle various IR types."""
    from polyphony.compiler.ir.transformers.inlineopt import _StmsVisitor
    from polyphony.compiler.ir.ir import (
        UnOp, BinOp, RelOp, CondOp, MRef, MStore, Array,
        CExpr, CMove, MCJump, Phi, UPhi, LPhi, MStm, Expr, Ret as RetIr,
        Attr as AttrIr,
    )

    setup_test()
    top = Scope.global_scope()
    F = Scope.create(top, 'f', {'function'}, 0)
    F.add_sym('x', tags=set(), typ=Type.int())
    F.add_sym('y', tags=set(), typ=Type.int())
    F.return_type = Type.none()
    blk = Block(F, nametag='blk1')
    blk2 = Block(F, nametag='blk2')
    blk3 = Block(F, nametag='blk3')
    F.set_entry_block(blk)
    F.set_exit_block(blk)

    visitor = _StmsVisitor()
    visitor.scope = F
    visitor.current_stm = None

    # Exercise IrExp visitor methods
    visitor.visit(UnOp(op='Not', exp=Temp('x')))
    visitor.visit(BinOp(op='Add', left=Temp('x'), right=Const(1)))
    visitor.visit(RelOp(op='Eq', left=Temp('x'), right=Const(1)))
    visitor.visit(CondOp(cond=Temp('x'), left=Const(1), right=Const(2)))
    visitor.visit(MRef(mem=Temp('x'), offset=Const(0)))
    visitor.visit(MStore(mem=Temp('x'), offset=Const(0), exp=Const(1)))
    visitor.visit(Array(items=[Temp('x'), Const(1)], repeat=Const(1)))
    # Array with None repeat
    visitor.visit(Array(items=[Temp('x')], repeat=None))
    visitor.visit(Const(value=42))
    visitor.visit(Temp(name='x'))
    visitor.visit(AttrIr(name='x', exp=Temp('y'), attr='x'))

    # Exercise IrStm visitor methods
    expr_stm = Expr(exp=Temp('x'), block=blk)
    visitor.visit(expr_stm)

    cexpr = CExpr(cond=Const(1), exp=Temp('x'), block=blk)
    visitor.visit(cexpr)

    mv = Move(Temp('y', OldCtx.STORE), Temp('x'), block=blk)
    visitor.visit(mv)

    cmove = CMove(cond=Const(1), dst=Temp('y', OldCtx.STORE), src=Temp('x'), block=blk)
    visitor.visit(cmove)

    from polyphony.compiler.ir.ir import CJump as CJumpIr
    cjump = CJumpIr(exp=Temp('x'), true=blk2, false=blk3, block=blk)
    visitor.visit(cjump)

    mcjump = MCJump(conds=[Const(1), Const(1)], targets=[blk2, blk3], block=blk)
    visitor.visit(mcjump)

    jmp = Jump(blk2, block=blk)
    visitor.visit(jmp)

    ret = RetIr(exp=Temp('x'), block=blk)
    visitor.visit(ret)

    phi = Phi(var=Temp('x', OldCtx.STORE),
              args=[Const(1), Const(None)],
              ps=[Const(1), Const(None)],
              block=blk)
    visitor.visit(phi)

    uphi = UPhi(var=Temp('x', OldCtx.STORE), args=[Const(1)], ps=[Const(1)], block=blk)
    visitor.visit(uphi)

    lphi = LPhi(var=Temp('x', OldCtx.STORE), args=[Const(1)], ps=[Const(1)], block=blk)
    visitor.visit(lphi)

    # MStm
    inner_stm = Move(Temp('x', OldCtx.STORE), Const(1), block=blk)
    mstm = MStm(stms=[inner_stm], block=blk)
    visitor.visit(mstm)

    # visit with unknown IR type (returns None)
    class FakeIr:
        pass
    result = visitor.visit(FakeIr())
    assert result is None


def test_stms_transformer_transform_methods():
    """_StmsTransformer should process various statement types."""
    from polyphony.compiler.ir.transformers.inlineopt import _StmsTransformer
    from polyphony.compiler.ir.ir import (
        CExpr, CMove, MCJump as MCJumpIr, Phi, UPhi, LPhi, MStm,
        CJump as CJumpIr, Ret as RetIr, Expr as ExprIr,
        Attr as AttrIr, UnOp, BinOp, RelOp, CondOp,
        MRef, MStore, Array, Call as CallIr, SysCall, New as NewIr,
    )

    setup_test()
    top = Scope.global_scope()
    F = Scope.create(top, 'f', {'function'}, 0)
    F.add_sym('x', tags=set(), typ=Type.int())
    F.add_sym('y', tags=set(), typ=Type.int())
    F.add_sym('fn', tags=set(), typ=Type.int())
    F.return_type = Type.none()
    blk = Block(F, nametag='blk1')
    blk2 = Block(F, nametag='blk2')
    blk3 = Block(F, nametag='blk3')
    F.set_entry_block(blk)
    F.set_exit_block(blk)
    Block.set_order(blk, 0)
    transformer = _StmsTransformer()

    # Test Expr
    expr = ExprIr(exp=Temp('x'), block=blk)
    blk.stms = [expr]
    transformer.process(F)
    assert len(blk.stms) == 1

    # Test CExpr
    cexpr = CExpr(cond=Const(1), exp=Temp('x'), block=blk)
    blk.stms = [cexpr]
    transformer.process(F)
    assert len(blk.stms) == 1
    assert isinstance(blk.stms[0], CExpr)

    # Test Move
    mv = Move(Temp('y', OldCtx.STORE), Temp('x'), block=blk)
    blk.stms = [mv]
    transformer.process(F)
    assert len(blk.stms) == 1

    # Test CMove
    cmove = CMove(cond=Const(1), dst=Temp('y', OldCtx.STORE), src=Temp('x'), block=blk)
    blk.stms = [cmove]
    transformer.process(F)
    assert len(blk.stms) == 1
    assert isinstance(blk.stms[0], CMove)

    # Test CJump
    cjump = CJumpIr(exp=Temp('x'), true=blk2, false=blk3, block=blk)
    blk.stms = [cjump]
    transformer.process(F)
    assert len(blk.stms) == 1

    # Test MCJump
    mcjump = MCJumpIr(conds=[Const(1), Const(1)], targets=[blk2, blk3], block=blk)
    blk.stms = [mcjump]
    transformer.process(F)
    assert len(blk.stms) == 1

    # Test Jump
    jmp = Jump(blk2, block=blk)
    blk.stms = [jmp]
    transformer.process(F)
    assert len(blk.stms) == 1

    # Test Ret
    ret = RetIr(exp=Temp('x'), block=blk)
    blk.stms = [ret]
    transformer.process(F)
    assert len(blk.stms) == 1

    # Test Phi
    phi = Phi(var=Temp('x', OldCtx.STORE),
              args=[Const(1), Const(2)],
              ps=[Const(1), Const(1)],
              block=blk)
    blk.stms = [phi]
    transformer.process(F)
    assert len(blk.stms) == 1
    assert isinstance(blk.stms[0], Phi)

    # Test Phi with no ps
    phi_no_ps = Phi(var=Temp('x', OldCtx.STORE),
                    args=[Const(1)],
                    ps=[],
                    block=blk)
    blk.stms = [phi_no_ps]
    transformer.process(F)
    assert len(blk.stms) == 1

    # Test UPhi
    uphi = UPhi(var=Temp('x', OldCtx.STORE),
                args=[Const(1)],
                ps=[Const(1)],
                block=blk)
    blk.stms = [uphi]
    transformer.process(F)
    assert len(blk.stms) == 1

    # Test LPhi
    lphi = LPhi(var=Temp('x', OldCtx.STORE),
                args=[Const(1)],
                ps=[Const(1)],
                block=blk)
    blk.stms = [lphi]
    transformer.process(F)
    assert len(blk.stms) == 1

    # Test MStm
    inner = Move(Temp('x', OldCtx.STORE), Const(1), block=blk)
    mstm = MStm(stms=[inner], block=blk)
    blk.stms = [mstm]
    transformer.process(F)
    assert len(blk.stms) == 1
    assert isinstance(blk.stms[0], MStm)

    # Test IrExp transformers: UnOp, BinOp, RelOp, CondOp, Call, SysCall, New,
    # Attr, MRef, MStore, Array (via Expr wrapping)
    blk.stms = [ExprIr(exp=UnOp(op='Not', exp=Temp('x')), block=blk)]
    transformer.process(F)
    assert len(blk.stms) == 1

    blk.stms = [ExprIr(exp=BinOp(op='Add', left=Temp('x'), right=Const(1)), block=blk)]
    transformer.process(F)
    assert len(blk.stms) == 1

    blk.stms = [ExprIr(exp=RelOp(op='Eq', left=Temp('x'), right=Const(1)), block=blk)]
    transformer.process(F)
    assert len(blk.stms) == 1

    blk.stms = [ExprIr(exp=CondOp(cond=Temp('x'), left=Const(1), right=Const(2)), block=blk)]
    transformer.process(F)
    assert len(blk.stms) == 1

    blk.stms = [ExprIr(exp=CallIr(func=Temp('fn'), args=[('', Temp('x'))], kwargs={}), block=blk)]
    transformer.process(F)
    assert len(blk.stms) == 1

    F.add_sym('$fn', tags=set(), typ=Type.int())
    blk.stms = [ExprIr(exp=SysCall(func=Temp('$fn'), args=[('', Temp('x'))], kwargs={}), block=blk)]
    transformer.process(F)
    assert len(blk.stms) == 1

    F.add_sym('C', tags=set(), typ=Type.int())
    blk.stms = [ExprIr(exp=NewIr(func=Temp('C'), args=[('', Temp('x'))], kwargs={}), block=blk)]
    transformer.process(F)
    assert len(blk.stms) == 1

    blk.stms = [ExprIr(exp=AttrIr(name='x', exp=Temp('y'), attr='x'), block=blk)]
    transformer.process(F)
    assert len(blk.stms) == 1

    blk.stms = [ExprIr(exp=MRef(mem=Temp('x'), offset=Const(0)), block=blk)]
    transformer.process(F)
    assert len(blk.stms) == 1

    blk.stms = [ExprIr(exp=MStore(mem=Temp('x'), offset=Const(0), exp=Const(1)), block=blk)]
    transformer.process(F)
    assert len(blk.stms) == 1

    blk.stms = [ExprIr(exp=Array(items=[Temp('x')], repeat=Const(1)), block=blk)]
    transformer.process(F)
    assert len(blk.stms) == 1

    # Array with None repeat
    blk.stms = [ExprIr(exp=Array(items=[Temp('x')], repeat=None), block=blk)]
    transformer.process(F)
    assert len(blk.stms) == 1


def test_new_inline_opt_simple_inline():
    """InlineOpt should inline a simple function call."""
    setup_test()
    top = Scope.global_scope()

    # Create callee: def add1(x): return x + 1
    callee = Scope.create(top, 'add1', {'function', 'returnable'}, 0)
    x_param_sym = callee.add_param_sym('x', set(), typ=Type.int())
    callee.add_param(x_param_sym, None)
    # Also add 'x' as a local symbol (param copy)
    callee.add_sym('x', tags=set(), typ=Type.int())
    ret_sym = callee.add_return_sym()
    callee.return_type = Type.int()
    callee_blk = Block(callee, nametag='blk1')
    callee.set_entry_block(callee_blk)
    callee.set_exit_block(callee_blk)
    from polyphony.compiler.ir.ir import BinOp
    # param copy: x = @in_x
    callee_blk.append_stm(Move(Temp('x', OldCtx.STORE), Temp(x_param_sym.name)))
    callee_blk.append_stm(Move(Temp(ret_sym.name, OldCtx.STORE), BinOp('Add', Temp('x'), Const(1))))
    callee_blk.append_stm(Ret(Temp(ret_sym.name)))
    Block.set_order(callee_blk, 0)
    callee_sym = top.add_sym('add1', tags=set(), typ=Type.function(callee, Type.int(), (Type.int(),)))

    # Create testbench caller
    caller = Scope.create(top, 'test', {'function', 'testbench'}, 0)
    caller.add_sym('result', tags=set(), typ=Type.int())
    caller.import_sym(callee_sym)
    caller.return_type = Type.none()
    caller_blk = Block(caller, nametag='blk1')
    caller.set_entry_block(caller_blk)
    caller.set_exit_block(caller_blk)
    call = Call(Temp('add1'), args=[('x', Const(5))], kwargs={})
    caller_blk.append_stm(Move(Temp('result', OldCtx.STORE), call))
    Block.set_order(caller_blk, 0)

    # Run InlineOpt
    scopes = InlineOpt().process_scopes([caller])

    # After inlining, the CALL should be gone from the caller
    all_stms = []
    for blk in caller.traverse_blocks():
        all_stms.extend(blk.stms)
    # Should not have any CALL to add1
    has_call = False
    for stm in all_stms:
        if isinstance(stm, Move) and isinstance(stm.src, Call):
            has_call = True
    assert not has_call, 'CALL should have been inlined'
