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
    """IrReplacer should replace variables based on symbol map."""
    from polyphony.compiler.ir.transformers.inlineopt import IrReplacer

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
    IrReplacer(replace_map).process(F, F.entry_block)

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


def test_inline_returnable_in_expr_statement():
    """InlineOpt handles returnable function call in Expr (discarding return value)."""
    setup_test()
    top = Scope.global_scope()

    # Create callee: def side_effect(x): return x + 1
    callee = Scope.create(top, 'side_effect', {'function', 'returnable'}, 0)
    x_param = callee.add_param_sym('x', set(), typ=Type.int())
    callee.add_param(x_param, None)
    callee.add_sym('x', tags=set(), typ=Type.int())
    ret_sym = callee.add_return_sym()
    callee.return_type = Type.int()
    callee_blk = Block(callee, nametag='blk1')
    callee.set_entry_block(callee_blk)
    callee.set_exit_block(callee_blk)
    from polyphony.compiler.ir.ir import BinOp
    callee_blk.append_stm(Move(Temp('x', OldCtx.STORE), Temp(x_param.name)))
    callee_blk.append_stm(Move(Temp(ret_sym.name, OldCtx.STORE), BinOp('Add', Temp('x'), Const(1))))
    callee_blk.append_stm(Ret(Temp(ret_sym.name)))
    Block.set_order(callee_blk, 0)
    callee_sym = top.add_sym('side_effect', tags=set(), typ=Type.function(callee, Type.int(), (Type.int(),)))

    # Create caller that calls side_effect in an Expr statement
    caller = Scope.create(top, 'test_caller', {'function'}, 0)
    caller.import_sym(callee_sym)
    caller.return_type = Type.none()
    caller_blk = Block(caller, nametag='blk1')
    caller.set_entry_block(caller_blk)
    caller.set_exit_block(caller_blk)
    call = Call(Temp('side_effect'), args=[('x', Const(5))], kwargs={})
    caller_blk.append_stm(Expr(exp=call))
    Block.set_order(caller_blk, 0)

    InlineOpt().process_scopes([caller])

    # The Expr(Call) should be gone after inlining
    all_stms = []
    for blk in caller.traverse_blocks():
        all_stms.extend(blk.stms)
    for stm in all_stms:
        if isinstance(stm, Expr):
            assert not isinstance(stm.exp, Call), 'Expr(Call) should have been inlined'


def test_inline_skip_testbench_callee():
    """InlineOpt skips inlining when callee is a testbench."""
    setup_test()
    top = Scope.global_scope()

    # Create testbench callee
    callee = Scope.create(top, 'tb', {'function', 'testbench'}, 0)
    callee.return_type = Type.none()
    callee_blk = Block(callee, nametag='blk1')
    callee.set_entry_block(callee_blk)
    callee.set_exit_block(callee_blk)
    callee_blk.append_stm(Ret(Const(0)))
    Block.set_order(callee_blk, 0)
    callee_sym = top.add_sym('tb', tags=set(), typ=Type.function(callee, Type.none(), ()))

    # Create caller
    caller = Scope.create(top, 'main', {'function'}, 0)
    caller.import_sym(callee_sym)
    caller.return_type = Type.none()
    caller_blk = Block(caller, nametag='blk1')
    caller.set_entry_block(caller_blk)
    caller.set_exit_block(caller_blk)
    call = Call(Temp('tb'), args=[], kwargs={})
    caller_blk.append_stm(Expr(exp=call))
    Block.set_order(caller_blk, 0)

    InlineOpt().process_scopes([caller])

    # Call should still exist (testbench not inlined)
    has_call = False
    for blk in caller.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Expr) and isinstance(stm.exp, Call):
                has_call = True
    assert has_call, 'Testbench call should NOT have been inlined'


def test_reduce_useless_move():
    """_reduce_useless_move removes mv x x statements."""
    setup_test()
    top = Scope.global_scope()

    F = Scope.create(top, 'f', {'function'}, 0)
    F.add_sym('x', tags=set(), typ=Type.int())
    F.return_type = Type.none()
    blk = Block(F, nametag='blk1')
    F.set_entry_block(blk)
    F.set_exit_block(blk)
    # Add a useless move: x = x
    blk.append_stm(Move(Temp('x', OldCtx.STORE), Temp('x')))
    # Add a normal move
    blk.append_stm(Move(Temp('x', OldCtx.STORE), Const(10)))
    Block.set_order(blk, 0)

    opt = InlineOpt()
    opt._reduce_useless_move(F)

    # The useless move should be removed, the normal one should remain
    assert len(blk.stms) == 1
    assert isinstance(blk.stms[0].src, Const) and blk.stms[0].src.value == 10


def test_flatten_module_no_parent():
    """FlattenModule returns empty for scopes without module parent."""
    from polyphony.compiler.ir.transformers.inlineopt import FlattenModule
    setup_test()
    top = Scope.global_scope()

    F = Scope.create(top, 'standalone', {'function'}, 0)
    F.return_type = Type.none()
    blk = Block(F, nametag='blk1')
    F.set_entry_block(blk)
    F.set_exit_block(blk)
    Block.set_order(blk, 0)

    result = FlattenModule().process(F)
    assert result == [] or len(result) == 0


def test_new_call_collector_for_flatten():
    """_NewCallCollectorForFlatten collects Call nodes."""
    from polyphony.compiler.ir.transformers.inlineopt import _NewCallCollectorForFlatten
    setup_test()
    top = Scope.global_scope()

    callee = Scope.create(top, 'g', {'function'}, 0)
    callee.return_type = Type.int()
    callee_blk = Block(callee, nametag='blk1')
    callee.set_entry_block(callee_blk)
    callee.set_exit_block(callee_blk)
    callee_blk.append_stm(Ret(Const(0)))
    Block.set_order(callee_blk, 0)
    top.add_sym('g', tags=set(), typ=Type.function(callee, Type.int(), ()))

    F = Scope.create(top, 'f', {'function'}, 0)
    F.import_sym(top.find_sym('g'))
    F.add_sym('result', tags=set(), typ=Type.int())
    F.return_type = Type.none()
    blk = Block(F, nametag='blk1')
    F.set_entry_block(blk)
    F.set_exit_block(blk)
    call = Call(Temp('g'), args=[], kwargs={})
    blk.append_stm(Move(Temp('result', OldCtx.STORE), call))
    Block.set_order(blk, 0)

    collector = _NewCallCollectorForFlatten()
    result = collector.process(F)
    assert len(result) == 1
    scope, stm, call_ir = result[0]
    assert isinstance(call_ir, Call)


def _make_module_with_sub_worker():
    """Helper to create module hierarchy for FlattenModule tests.

    Creates:
      SubM (module class) with worker (method) and append_worker (method)
      M (module class) with sub:SubM
      M.__init__ (method ctor) as the scope to flatten
    """
    top = Scope.global_scope()

    # Sub-module SubM with a method worker
    SubM = Scope.create(top, 'SubM', {'module', 'class'}, 0)
    worker = Scope.create(SubM, 'worker', {'method'}, 0)
    worker_self = worker.add_param_sym('self', set(), typ=Type.object(SubM))
    worker.add_param(worker_self, None)
    worker.add_sym('self', tags=set(), typ=Type.object(SubM))
    worker.return_type = Type.none()
    w_blk = Block(worker, nametag='blk1')
    worker.set_entry_block(w_blk)
    worker.set_exit_block(w_blk)
    Block.set_order(w_blk, 0)
    SubM.add_sym('worker', tags=set(), typ=Type.function(worker))

    # append_worker method on SubM
    aw = Scope.create(SubM, 'append_worker', {'method'}, 0)
    aw_self = aw.add_param_sym('self', set(), typ=Type.object(SubM))
    aw.add_param(aw_self, None)
    aw.add_sym('self', tags=set(), typ=Type.object(SubM))
    aw.return_type = Type.none()
    aw_blk = Block(aw, nametag='blk1')
    aw.set_entry_block(aw_blk)
    aw.set_exit_block(aw_blk)
    Block.set_order(aw_blk, 0)
    SubM.add_sym('append_worker', tags=set(), typ=Type.function(aw))
    top.add_sym('SubM', tags=set(), typ=Type.klass(SubM))

    # Parent module M with sub:SubM
    M = Scope.create(top, 'M', {'module', 'class'}, 0)
    M.add_sym('sub', tags=set(), typ=Type.object(SubM))
    top.add_sym('M', tags=set(), typ=Type.klass(M))

    # M.__init__
    init = Scope.create(M, '__init__', {'method', 'ctor'}, 0)
    init_self = init.add_param_sym('self', set(), typ=Type.object(M))
    init.add_param(init_self, None)
    init.add_sym('self', tags=set(), typ=Type.object(M))
    init.import_sym(SubM.find_sym('append_worker'))
    init.import_sym(SubM.find_sym('worker'))
    init.return_type = Type.object(M)
    M.add_sym('__init__', tags=set(), typ=Type.function(init))

    return top, SubM, M, init


def test_flatten_module_method_worker():
    """FlattenModule flattens self.sub.append_worker(self.sub.worker)."""
    setup_test()
    top, SubM, M, init = _make_module_with_sub_worker()

    init_blk = Block(init, nametag='blk1')
    init.set_entry_block(init_blk)
    init.set_exit_block(init_blk)

    # self.sub.append_worker(self.sub.worker)
    func_attr = Attr(name='append_worker',
                     exp=Attr(name='sub', exp=Temp('self'), attr='sub'),
                     attr='append_worker', ctx=OldCtx.CALL)
    arg_attr = Attr(name='worker',
                    exp=Attr(name='sub', exp=Temp('self'), attr='sub'),
                    attr='worker', ctx=OldCtx.LOAD)
    call = Call(func=func_attr, args=[('', arg_attr)], kwargs={})
    init_blk.append_stm(Expr(exp=call))
    Block.set_order(init_blk, 0)

    new_scopes = FlattenModule().process(init)

    # Should create a new worker scope
    assert len(new_scopes) == 1

    # The call should be rewritten to self.append_worker(self.sub_worker)
    blk = next(init.traverse_blocks())
    stm = blk.stms[0]
    assert isinstance(stm, Expr)
    assert isinstance(stm.exp, Call)
    assert stm.exp.func.exp.name == 'self'
    assert stm.exp.func.name == 'append_worker'


def test_flatten_module_nonmethod_worker():
    """FlattenModule rewrites but does not clone non-method workers."""
    setup_test()
    top = Scope.global_scope()

    # Sub-module with a function (not method) worker
    SubM = Scope.create(top, 'SubM', {'module', 'class'}, 0)
    worker = Scope.create(SubM, 'worker_fn', {'function'}, 0)
    worker.return_type = Type.none()
    w_blk = Block(worker, nametag='blk1')
    worker.set_entry_block(w_blk)
    worker.set_exit_block(w_blk)
    Block.set_order(w_blk, 0)
    SubM.add_sym('worker_fn', tags=set(), typ=Type.function(worker))

    aw = Scope.create(SubM, 'append_worker', {'method'}, 0)
    aw_self = aw.add_param_sym('self', set(), typ=Type.object(SubM))
    aw.add_param(aw_self, None)
    aw.add_sym('self', tags=set(), typ=Type.object(SubM))
    aw.return_type = Type.none()
    aw_blk = Block(aw, nametag='blk1')
    aw.set_entry_block(aw_blk)
    aw.set_exit_block(aw_blk)
    Block.set_order(aw_blk, 0)
    SubM.add_sym('append_worker', tags=set(), typ=Type.function(aw))
    top.add_sym('SubM', tags=set(), typ=Type.klass(SubM))

    M = Scope.create(top, 'M', {'module', 'class'}, 0)
    M.add_sym('sub', tags=set(), typ=Type.object(SubM))
    top.add_sym('M', tags=set(), typ=Type.klass(M))

    init = Scope.create(M, '__init__', {'method', 'ctor'}, 0)
    init_self = init.add_param_sym('self', set(), typ=Type.object(M))
    init.add_param(init_self, None)
    init.add_sym('self', tags=set(), typ=Type.object(M))
    init.import_sym(SubM.find_sym('append_worker'))
    init.import_sym(SubM.find_sym('worker_fn'))
    init.return_type = Type.object(M)
    M.add_sym('__init__', tags=set(), typ=Type.function(init))

    init_blk = Block(init, nametag='blk1')
    init.set_entry_block(init_blk)
    init.set_exit_block(init_blk)

    func_attr = Attr(name='append_worker',
                     exp=Attr(name='sub', exp=Temp('self'), attr='sub'),
                     attr='append_worker', ctx=OldCtx.CALL)
    arg_attr = Attr(name='worker_fn',
                    exp=Attr(name='sub', exp=Temp('self'), attr='sub'),
                    attr='worker_fn', ctx=OldCtx.LOAD)
    call = Call(func=func_attr, args=[('', arg_attr)], kwargs={})
    init_blk.append_stm(Expr(exp=call))
    Block.set_order(init_blk, 0)

    new_scopes = FlattenModule().process(init)

    # Non-method worker: no new scope cloned
    assert len(new_scopes) == 0

    # The call should be rewritten to self.append_worker(...)
    blk = next(init.traverse_blocks())
    stm = blk.stms[0]
    assert isinstance(stm, Expr)
    assert isinstance(stm.exp, Call)
    assert stm.exp.func.exp.name == 'self'
    assert stm.exp.func.name == 'append_worker'
    # arg should have None key (not '')
    assert stm.exp.args[0][0] is None


def test_flatten_module_else_branch():
    """FlattenModule else branch visits args of non-append_worker calls."""
    setup_test()
    top = Scope.global_scope()

    # Module with a regular method (not append_worker)
    M = Scope.create(top, 'M', {'module', 'class'}, 0)
    top.add_sym('M', tags=set(), typ=Type.klass(M))

    regular = Scope.create(M, 'regular', {'method'}, 0)
    reg_self = regular.add_param_sym('self', set(), typ=Type.object(M))
    regular.add_param(reg_self, None)
    regular.add_sym('self', tags=set(), typ=Type.object(M))
    regular.return_type = Type.none()
    r_blk = Block(regular, nametag='blk1')
    regular.set_entry_block(r_blk)
    regular.set_exit_block(r_blk)
    Block.set_order(r_blk, 0)
    M.add_sym('regular', tags=set(), typ=Type.function(regular))

    init = Scope.create(M, '__init__', {'method', 'ctor'}, 0)
    init_self = init.add_param_sym('self', set(), typ=Type.object(M))
    init.add_param(init_self, None)
    init.add_sym('self', tags=set(), typ=Type.object(M))
    init.import_sym(M.find_sym('regular'))
    init.return_type = Type.object(M)
    M.add_sym('__init__', tags=set(), typ=Type.function(init))

    init_blk = Block(init, nametag='blk1')
    init.set_entry_block(init_blk)
    init.set_exit_block(init_blk)

    func_attr = Attr(name='regular', exp=Temp('self'), attr='regular', ctx=OldCtx.CALL)
    call = Call(func=func_attr, args=[('', Const(42))], kwargs={})
    init_blk.append_stm(Expr(exp=call))
    Block.set_order(init_blk, 0)

    new_scopes = FlattenModule().process(init)
    assert len(new_scopes) == 0

    # Call should remain unchanged
    blk = next(init.traverse_blocks())
    stm = blk.stms[0]
    assert isinstance(stm, Expr)
    assert isinstance(stm.exp, Call)
    assert stm.exp.func.name == 'regular'


def test_flatten_module_port_assign():
    """FlattenModule handles self.sub.p.assign(self.sub.handler) for port assign."""
    from pytests.compiler.base import setup_libs
    setup_test()
    setup_libs('io')
    top = Scope.global_scope()

    PortScope = env.scopes['polyphony.io.Port']

    # Sub-module with an assigned method and a port
    SubM = Scope.create(top, 'SubM', {'module', 'class'}, 0)

    handler = Scope.create(SubM, 'handler', {'method', 'assigned'}, 0)
    h_self = handler.add_param_sym('self', set(), typ=Type.object(SubM))
    handler.add_param(h_self, None)
    handler.add_sym('self', tags=set(), typ=Type.object(SubM))
    handler.return_type = Type.int()
    h_blk = Block(handler, nametag='blk1')
    handler.set_entry_block(h_blk)
    handler.set_exit_block(h_blk)
    h_blk.append_stm(Ret(Const(0)))
    Block.set_order(h_blk, 0)
    SubM.add_sym('handler', tags=set(), typ=Type.function(handler))
    SubM.add_sym('p', tags=set(), typ=Type.object(PortScope))
    top.add_sym('SubM', tags=set(), typ=Type.klass(SubM))

    # Parent module M
    M = Scope.create(top, 'M', {'module', 'class'}, 0)
    M.add_sym('sub', tags=set(), typ=Type.object(SubM))
    top.add_sym('M', tags=set(), typ=Type.klass(M))

    # M.__init__
    init = Scope.create(M, '__init__', {'method', 'ctor'}, 0)
    init_self = init.add_param_sym('self', set(), typ=Type.object(M))
    init.add_param(init_self, None)
    init.add_sym('self', tags=set(), typ=Type.object(M))
    init.import_sym(PortScope.find_sym('assign'))
    init.import_sym(SubM.find_sym('handler'))
    init.return_type = Type.object(M)
    M.add_sym('__init__', tags=set(), typ=Type.function(init))

    init_blk = Block(init, nametag='blk1')
    init.set_entry_block(init_blk)
    init.set_exit_block(init_blk)

    # self.sub.p.assign(self.sub.handler) -- qualified_name length 4
    func_attr = Attr(name='assign',
                     exp=Attr(name='p',
                              exp=Attr(name='sub', exp=Temp('self'), attr='sub'),
                              attr='p'),
                     attr='assign', ctx=OldCtx.CALL)
    arg_attr = Attr(name='handler',
                    exp=Attr(name='sub', exp=Temp('self'), attr='sub'),
                    attr='handler', ctx=OldCtx.LOAD)
    call = Call(func=func_attr, args=[('', arg_attr)], kwargs={})
    init_blk.append_stm(Expr(exp=call))
    Block.set_order(init_blk, 0)

    new_scopes = FlattenModule().process(init)

    # Should create a new assigned method scope
    assert len(new_scopes) == 1

    # The arg should be rewritten
    blk = next(init.traverse_blocks())
    stm = blk.stms[0]
    assert isinstance(stm, Expr)
    assert isinstance(stm.exp, Call)
    _, new_arg = stm.exp.args[0]
    assert isinstance(new_arg, Attr)
    assert new_arg.exp.name == 'self'


def test_inline_skips_testbench_module_ctor():
    """InlineOpt does NOT inline module ctor when caller is testbench."""
    setup_test()
    top = Scope.global_scope()

    # Module M with ctor
    M = Scope.create(top, 'M', {'module', 'class'}, 0)
    M.add_sym('x', tags=set(), typ=Type.int(32))
    top.add_sym('M', tags=set(), typ=Type.klass(M))

    ctor = Scope.create(M, '__init__', {'method', 'ctor'}, 0)
    ctor_self = ctor.add_param_sym('self', set(), typ=Type.object(M))
    ctor.add_param(ctor_self, None)
    ctor.add_sym('self', tags=set(), typ=Type.object(M))
    ctor.return_type = Type.object(M)
    ctor_blk = Block(ctor, nametag='blk1')
    ctor.set_entry_block(ctor_blk)
    ctor.set_exit_block(ctor_blk)
    ctor_blk.append_stm(Move(Temp('self.x', OldCtx.STORE), Const(0)))
    Block.set_order(ctor_blk, 0)
    M.add_sym('__init__', tags=set(), typ=Type.function(ctor))

    # Testbench
    tb = Scope.create(top, 'test', {'function', 'testbench'}, 0)
    tb.add_sym('m', tags=set(), typ=Type.object(M))
    tb.import_sym(top.find_sym('M'))
    tb.return_type = Type.none()
    tb_blk = Block(tb, nametag='blk1')
    tb.set_entry_block(tb_blk)
    tb.set_exit_block(tb_blk)
    tb_blk.append_stm(Move(Temp('m', OldCtx.STORE), New(Temp('M'), args=[], kwargs={})))
    Block.set_order(tb_blk, 0)

    InlineOpt().process_scopes([tb])

    # New(M) should NOT be inlined (testbench + module ctor)
    has_new = False
    for blk in tb.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.src, New):
                has_new = True
    assert has_new, 'Module ctor should not be inlined in testbench'


def test_inline_skips_testbench_callee():
    """InlineOpt does NOT inline testbench callees."""
    setup_test()
    top = Scope.global_scope()

    # Testbench callee
    tb_callee = Scope.create(top, 'tb_callee', {'function', 'testbench'}, 0)
    tb_callee.return_type = Type.none()
    tb_blk = Block(tb_callee, nametag='blk1')
    tb_callee.set_entry_block(tb_blk)
    tb_callee.set_exit_block(tb_blk)
    Block.set_order(tb_blk, 0)
    top.add_sym('tb_callee', tags=set(), typ=Type.function(tb_callee, Type.none(), ()))

    # Caller
    caller = Scope.create(top, 'main', {'function'}, 0)
    caller.import_sym(top.find_sym('tb_callee'))
    caller.return_type = Type.none()
    caller_blk = Block(caller, nametag='blk1')
    caller.set_entry_block(caller_blk)
    caller.set_exit_block(caller_blk)
    caller_blk.append_stm(Expr(exp=Call(Temp('tb_callee'), args=[], kwargs={})))
    Block.set_order(caller_blk, 0)

    InlineOpt().process_scopes([caller])

    # Call should remain (testbench not inlined)
    has_call = False
    for blk in caller.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Expr) and isinstance(stm.exp, Call):
                has_call = True
    assert has_call, 'Testbench callee should not be inlined'


def test_inline_skips_testbench_to_function_module():
    """InlineOpt skips function_module when caller is testbench (no perfect_inlining)."""
    setup_test()
    top = Scope.global_scope()

    # function_module callee
    callee = Scope.create(top, 'fm', {'function', 'function_module', 'returnable'}, 0)
    callee.add_sym('x', tags=set(), typ=Type.int())
    callee.return_type = Type.int()
    callee_blk = Block(callee, nametag='blk1')
    callee.set_entry_block(callee_blk)
    callee.set_exit_block(callee_blk)
    callee_blk.append_stm(Move(Temp('x', OldCtx.STORE), Const(42)))
    callee_blk.append_stm(Ret(Temp('x')))
    Block.set_order(callee_blk, 0)
    top.add_sym('fm', tags=set(), typ=Type.function(callee, Type.int(), ()))

    # Testbench caller
    tb = Scope.create(top, 'test', {'function', 'testbench'}, 0)
    tb.add_sym('result', tags=set(), typ=Type.int())
    tb.import_sym(top.find_sym('fm'))
    tb.return_type = Type.none()
    tb_blk = Block(tb, nametag='blk1')
    tb.set_entry_block(tb_blk)
    tb.set_exit_block(tb_blk)
    tb_blk.append_stm(Move(Temp('result', OldCtx.STORE), Call(Temp('fm'), args=[], kwargs={})))
    Block.set_order(tb_blk, 0)

    assert not env.config.perfect_inlining

    InlineOpt().process_scopes([tb])

    # Call should remain (testbench + function_module skip)
    has_call = False
    for blk in tb.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.src, Call):
                has_call = True
    assert has_call, 'function_module should not be inlined in testbench'


def test_inline_skips_namespace_to_method():
    """InlineOpt skips method when caller is namespace."""
    setup_test()
    top = Scope.global_scope()

    # Class C with method
    C = Scope.create(top, 'C', {'class'}, 0)
    top.add_sym('C', tags=set(), typ=Type.klass(C))

    meth = Scope.create(C, 'do_stuff', {'method'}, 0)
    m_self = meth.add_param_sym('self', set(), typ=Type.object(C))
    meth.add_param(m_self, None)
    meth.add_sym('self', tags=set(), typ=Type.object(C))
    meth.return_type = Type.none()
    m_blk = Block(meth, nametag='blk1')
    meth.set_entry_block(m_blk)
    meth.set_exit_block(m_blk)
    Block.set_order(m_blk, 0)
    C.add_sym('do_stuff', tags=set(), typ=Type.function(meth))

    # Namespace caller
    ns = Scope.create(top, 'ns', {'namespace'}, 0)
    ns.add_sym('c', tags=set(), typ=Type.object(C))
    ns.import_sym(C.find_sym('do_stuff'))
    ns.return_type = Type.none()
    ns_blk = Block(ns, nametag='blk1')
    ns.set_entry_block(ns_blk)
    ns.set_exit_block(ns_blk)
    call = Call(Attr(name='do_stuff', exp=Temp('c'), attr='do_stuff', ctx=OldCtx.CALL), args=[], kwargs={})
    ns_blk.append_stm(Expr(exp=call))
    Block.set_order(ns_blk, 0)

    assert ns.is_namespace()

    InlineOpt().process_scopes([ns])

    # Call should remain
    has_call = False
    for blk in ns.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Expr) and isinstance(stm.exp, Call):
                has_call = True
    assert has_call, 'Method should not be inlined in namespace'


def test_inline_with_perfect_inlining():
    """InlineOpt inlines function_module into testbench when perfect_inlining is True."""
    setup_test()
    top = Scope.global_scope()

    # function_module callee
    callee = Scope.create(top, 'fm', {'function', 'function_module', 'returnable'}, 0)
    callee_x = callee.add_param_sym('x', set(), typ=Type.int())
    callee.add_param(callee_x, None)
    callee.add_sym('x', tags=set(), typ=Type.int())
    callee_ret = callee.add_return_sym()
    callee.return_type = Type.int()
    callee_blk = Block(callee, nametag='blk1')
    callee.set_entry_block(callee_blk)
    callee.set_exit_block(callee_blk)
    callee_blk.append_stm(Move(Temp('x', OldCtx.STORE), Temp(callee_x.name)))
    callee_blk.append_stm(Move(Temp(callee_ret.name, OldCtx.STORE), Const(42)))
    callee_blk.append_stm(Ret(Temp(callee_ret.name)))
    Block.set_order(callee_blk, 0)
    top.add_sym('fm', tags=set(), typ=Type.function(callee, Type.int(), (Type.int(),)))

    # Testbench caller
    tb = Scope.create(top, 'test', {'function', 'testbench'}, 0)
    tb.add_sym('result', tags=set(), typ=Type.int())
    tb.import_sym(top.find_sym('fm'))
    tb.return_type = Type.none()
    tb_blk = Block(tb, nametag='blk1')
    tb.set_entry_block(tb_blk)
    tb.set_exit_block(tb_blk)
    tb_blk.append_stm(Move(Temp('result', OldCtx.STORE), Call(Temp('fm'), args=[('x', Const(5))], kwargs={})))
    Block.set_order(tb_blk, 0)

    # Enable perfect inlining
    old_val = env.config.perfect_inlining
    env.config.perfect_inlining = True
    try:
        InlineOpt().process_scopes([tb])
    finally:
        env.config.perfect_inlining = old_val

    # With perfect_inlining, function_module SHOULD be inlined into testbench
    has_call = False
    for blk in tb.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.src, Call):
                has_call = True
    assert not has_call, 'function_module should be inlined with perfect_inlining'


def test_flatten_module_port_assign_non_function_arg():
    """FlattenModule port assign returns early when arg is not function type."""
    from pytests.compiler.base import setup_libs
    setup_test()
    setup_libs('io')
    top = Scope.global_scope()

    PortScope = env.scopes['polyphony.io.Port']

    SubM = Scope.create(top, 'SubM', {'module', 'class'}, 0)
    SubM.add_sym('p', tags=set(), typ=Type.object(PortScope))
    SubM.add_sym('val', tags=set(), typ=Type.int(32))
    top.add_sym('SubM', tags=set(), typ=Type.klass(SubM))

    M = Scope.create(top, 'M', {'module', 'class'}, 0)
    M.add_sym('sub', tags=set(), typ=Type.object(SubM))
    top.add_sym('M', tags=set(), typ=Type.klass(M))

    init = Scope.create(M, '__init__', {'method', 'ctor'}, 0)
    init_self = init.add_param_sym('self', set(), typ=Type.object(M))
    init.add_param(init_self, None)
    init.add_sym('self', tags=set(), typ=Type.object(M))
    init.import_sym(PortScope.find_sym('assign'))
    init.import_sym(SubM.find_sym('val'))
    init.return_type = Type.object(M)
    M.add_sym('__init__', tags=set(), typ=Type.function(init))

    init_blk = Block(init, nametag='blk1')
    init.set_entry_block(init_blk)
    init.set_exit_block(init_blk)

    # self.sub.p.assign(self.sub.val) -- val is int, not function
    func_attr = Attr(name='assign',
                     exp=Attr(name='p',
                              exp=Attr(name='sub', exp=Temp('self'), attr='sub'),
                              attr='p'),
                     attr='assign', ctx=OldCtx.CALL)
    arg_attr = Attr(name='val',
                    exp=Attr(name='sub', exp=Temp('self'), attr='sub'),
                    attr='val', ctx=OldCtx.LOAD)
    call = Call(func=func_attr, args=[('', arg_attr)], kwargs={})
    init_blk.append_stm(Expr(exp=call))
    Block.set_order(init_blk, 0)

    new_scopes = FlattenModule().process(init)
    # Non-function arg: should return early, no changes
    assert len(new_scopes) == 0
