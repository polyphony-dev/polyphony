"""Helper functions for IR (ir.py).

Provides utility functions for working with IR nodes: type resolution,
expression evaluation, symbol qualification, and statement analysis.
"""

from __future__ import annotations
from typing import cast, Any, TYPE_CHECKING
from .ir import (
    IrExp,
    IrNameExp,
    IrVariable,
    IrStm,
    Temp,
    Attr,
    Ctx,
    Const,
    UnOp,
    BinOp,
    RelOp,
    Array,
    MRef,
    Call,
    SysCall,
    Move,
    Expr,
)
from .symbol import Symbol
from .types.scopetype import ScopeType
from .types.type import Type

if TYPE_CHECKING:
    from .scope import Scope


def qualified_symbols(ir: IrNameExp, scope: Scope) -> tuple[Symbol | str, ...]:
    """Resolve qualified name to symbol chain, using new IR types."""
    qname = ir.qualified_name
    # Fast path for single-element names (Temp variables — the common case)
    if len(qname) == 1:
        sym = scope.find_sym(qname[0])
        if sym:
            return (sym,)
        return (qname[0],)
    # Multi-element path (Attr chains)
    symbol_or_names: list[Symbol | str] = []
    for i, name in enumerate(qname):
        symbol = scope.find_sym(name)
        if symbol:
            assert isinstance(symbol, Symbol)
            symbol_or_names.append(symbol)
            if symbol.typ.has_scope():
                scope = cast(ScopeType, symbol.typ).scope
            else:
                symbol_or_names.extend(qname[i + 1 :])
                break
        else:
            symbol_or_names.extend(qname[i:])
            break
    assert len(symbol_or_names) == len(qname)
    return tuple(symbol_or_names)


def reduce_relexp(exp: IrExp) -> IrExp:
    """Simplify relational expressions by folding constant operands."""
    if isinstance(exp, RelOp):
        if exp.op == "And":
            new_left = reduce_relexp(exp.left)
            new_right = reduce_relexp(exp.right)
            if isinstance(new_left, Const):
                return new_right if new_left.value else Const(value=0)
            elif isinstance(new_left, UnOp) and new_left.op == "Not" and isinstance(new_left.exp, Const):
                return Const(value=0) if new_left.exp.value else new_right
            elif isinstance(new_right, Const):
                return new_left if new_right.value else Const(value=0)
            elif isinstance(new_right, UnOp) and new_right.op == "Not" and isinstance(new_right.exp, Const):
                return Const(value=0) if new_right.exp.value else new_left
            if new_left is not exp.left or new_right is not exp.right:
                return exp.model_copy(update={"left": new_left, "right": new_right})
        elif exp.op == "Or":
            new_left = reduce_relexp(exp.left)
            new_right = reduce_relexp(exp.right)
            if isinstance(new_left, Const):
                return Const(value=1) if new_left.value else new_right
            elif isinstance(new_left, UnOp) and new_left.op == "Not" and isinstance(new_left.exp, Const):
                return new_right if new_left.exp.value else Const(value=1)
            elif isinstance(new_right, Const):
                return Const(value=1) if new_right.value else new_left
            elif isinstance(new_right, UnOp) and new_right.op == "Not" and isinstance(new_right.exp, Const):
                return new_left if new_right.exp.value else Const(value=1)
            if new_left is not exp.left or new_right is not exp.right:
                return exp.model_copy(update={"left": new_left, "right": new_right})
    elif isinstance(exp, UnOp) and exp.op == "Not":
        nexp = reduce_relexp(exp.exp)
        if isinstance(nexp, Const):
            return Const(value=0) if nexp.value else Const(value=1)
        else:
            return UnOp(op="Not", exp=nexp)
    return exp


def reduce_binop(ir: BinOp) -> IrExp:
    """Simplify binary operations with constant operands (new IR version)."""
    if isinstance(ir.left, Const):
        const = ir.left.value
        var = ir.right
    elif isinstance(ir.right, Const):
        const = ir.right.value
        var = ir.left
    else:
        return ir
    if ir.op == "Add" and const == 0:
        return var
    elif ir.op == "Mult" and const == 1:
        return var
    elif ir.op == "Mult" and const == 0:
        return Const(value=0)
    return ir


def qsym2var(qsym: tuple, ctx: Ctx) -> IrVariable:
    """Convert a qualified symbol tuple to an IrVariable (Temp or Attr chain)."""
    assert len(qsym) > 0
    if len(qsym) == 1:
        return Temp(name=qsym[0].name, ctx=ctx)
    exp = Temp(name=qsym[0].name, ctx=Ctx.LOAD)
    for sym in qsym[1:-1]:
        exp = Attr(name=sym.name, exp=exp, attr=sym.name, ctx=Ctx.LOAD)
    exp = Attr(name=qsym[-1].name, exp=exp, attr=qsym[-1].name, ctx=ctx)
    return exp


def expr2ir(expr, name=None, scope=None):
    """Convert a Python value to an IR expression."""
    import inspect
    from ..common.env import env

    if expr is None:
        return Const(value=None)
    elif isinstance(expr, int):
        return Const(value=expr)
    elif isinstance(expr, str):
        return Const(value=expr)
    elif isinstance(expr, list):
        items = [expr2ir(e) for e in expr]
        ar = Array(items=items, mutable=True)
        return ar
    elif isinstance(expr, tuple):
        items = [expr2ir(e) for e in expr]
        ar = Array(items=items, mutable=False)
        return ar
    else:
        assert scope is not None, "scope is required for class/function expressions"
        if inspect.isclass(expr):
            if expr.__module__ == "polyphony.typing":
                klass_name = expr.__module__ + "." + expr.__name__
                klass_scope = env.scopes[klass_name]
                t = Type.klass(klass_scope)
                sym = scope.add_temp("@dtype", {"predefined"})
                sym.typ = t
            elif expr.__module__ == "builtins":
                klass_name = "__builtin__." + expr.__name__
                klass_scope = env.scopes[klass_name]
                t = Type.klass(klass_scope)
                sym = scope.add_temp("@dtype", {"predefined"})
                sym.typ = t
            else:
                assert False
            return Temp(name=sym.name)
        elif inspect.isfunction(expr):
            fsym = scope.find_sym(name)
            assert fsym.typ.is_function()
            return Temp(name=name)
        elif inspect.ismethod(expr):
            fsym = scope.find_sym(name)
            assert fsym.typ.is_function()
            return Temp(name=name)
        assert False


def eval_unop(op: str, v: int):
    """Evaluate a unary operation on a constant value."""
    if op == "Invert":
        return ~v
    elif op == "Not":
        return 1 if (not v) is True else 0
    elif op == "UAdd":
        return v
    elif op == "USub":
        return -v
    else:
        return None


def eval_binop(op: str, lv: Any, rv: Any) -> int | None:
    """Evaluate a binary operation on two constant values."""
    if op == "Add":
        return lv + rv
    elif op == "Sub":
        return lv - rv
    elif op == "Mult":
        return lv * rv
    elif op == "FloorDiv":
        return lv // rv
    elif op == "Mod":
        return lv % rv
    elif op == "LShift":
        return lv << rv
    elif op == "RShift":
        return lv >> rv
    elif op == "BitOr":
        return lv | rv
    elif op == "BitXor":
        return lv ^ rv
    elif op == "BitAnd":
        return lv & rv
    else:
        return None


def eval_relop(op: str, lv: Any, rv: Any) -> int | None:
    """Evaluate a relational operation on two constant values."""
    if op == "Eq":
        b = lv == rv
    elif op == "NotEq":
        b = lv != rv
    elif op == "Lt":
        b = lv < rv
    elif op == "LtE":
        b = lv <= rv
    elif op == "Gt":
        b = lv > rv
    elif op == "GtE":
        b = lv >= rv
    elif op == "Is":
        b = lv is rv
    elif op == "IsNot":
        b = lv is not rv
    elif op == "And":
        b = lv and rv
    elif op == "Or":
        b = lv or rv
    else:
        return None
    return 1 if b else 0


def irexp_type(ir: IrExp, scope: Scope) -> Type:
    """Determine the type of an IrExp node by resolving symbols."""
    match ir:
        case Array() as array:
            if array.items:
                elm_typ = irexp_type(array.items[0], scope)
            else:
                elm_typ = Type.none()
            if isinstance(array.repeat, Const):
                length = len(array.items) * array.repeat.value
            else:
                length = Type.ANY_LENGTH
            if array.mutable:
                return Type.list(elm_typ, length)
            else:
                return Type.tuple(elm_typ, length)
        case IrNameExp() as ir:
            qsym = qualified_symbols(ir, scope)
            assert isinstance(qsym[-1], Symbol)
            return qsym[-1].typ
        case MRef() as mref:
            return irexp_type(mref.mem, scope)
        case BinOp() as binop:
            return irexp_type(binop.left, scope)
        case RelOp():
            return Type.bool()
        case UnOp() as unop:
            return irexp_type(unop.exp, scope)
        case Const():
            return Type.int()
        case _:
            return Type.undef()


def is_port_method_call(call: Call, scope: Scope, callee_scope: Scope | None = None) -> bool:
    """Check if an IR node is a port method call (rd/wr/etc.)."""
    if not isinstance(call, Call):
        return False
    if callee_scope is None:
        callee_scope = _get_callee_scope(call, scope)
    return callee_scope.is_method() and callee_scope.parent.is_port()


def _get_callee_scope(call: Call, scope: Scope) -> Scope:
    """Resolve the callee scope for a Call node."""
    qsyms = qualified_symbols(call.func, scope)
    symbol = qsyms[-1]
    assert isinstance(symbol, Symbol)
    func_t = symbol.typ
    assert func_t.has_scope()
    return cast(ScopeType, func_t).scope


def has_clkfence(stm: IrStm) -> bool:
    """Check if a statement is a clkfence call (clksleep or wait_*)."""
    if not isinstance(stm, Expr):
        return False
    if not isinstance(stm.exp, SysCall):
        return False
    # Use func.name directly since IrCallable.name property doesn't work
    # correctly with pydantic field inheritance.
    name = stm.exp.func.name
    if name == "polyphony.timing.clksleep":
        return True
    if name.startswith("polyphony.timing.wait_"):
        return True
    return False


def has_exclusive_function(stm: IrStm, scope: Scope, callee_scope: Scope | None = None) -> bool:
    """Check if a statement contains an exclusive (scheduling-boundary) function."""
    if isinstance(stm, Move):
        call = stm.src
    elif isinstance(stm, Expr):
        call = stm.exp
    else:
        return False
    if isinstance(call, Call) and is_port_method_call(call, scope, callee_scope):
        if scope.find_block(stm.block).synth_params["scheduling"] == "timed":
            return False
        return True
    if has_clkfence(stm):
        return True
    return False


def find_move_src(sym: Symbol, typ: type) -> IrExp | None:
    """Find the source expression of a Move statement that assigns to sym with src of given type."""
    scope = sym.scope
    if scope.is_class():
        scope = scope.find_ctor()
    for block in scope.traverse_blocks():
        for stm in block.stms:
            if isinstance(stm, Move) and isinstance(stm.src, typ):
                if isinstance(stm.dst, IrVariable) and stm.dst.name == sym.name:
                    return stm.src
    return None


def is_mem_read(stm: IrStm) -> bool:
    """Check if a statement is a memory read (Move with MRef src)."""
    return isinstance(stm, Move) and isinstance(stm.src, MRef)


def is_mem_write(stm: IrStm) -> bool:
    """Check if a statement is a memory write (Expr with MStore exp)."""
    from .ir import MStore

    return isinstance(stm, Expr) and isinstance(stm.exp, MStore)


def program_order(stm: IrStm, scope: Scope) -> tuple[int, int]:
    """Get program order of a statement (block order, stm index in block.stms)."""
    from ..common.utils import find_id_index

    blk = scope.find_block(stm.block)
    return (blk.order, find_id_index(blk.stms, stm))


# ============================================================
# Constant lookup utilities
# ============================================================


def _try_get_constant(qsym: tuple[Symbol, ...], scope: Scope) -> IrExp | None:
    """Get constant value from scope.constants table."""
    sym = qsym[-1]
    if sym in sym.scope.constants:
        return sym.scope.constants[sym]
    return None


def _try_get_constant_pure(qsym: tuple[Symbol, ...], scope: Scope) -> IrExp | None:
    """Get constant value from runtime_info.global_vars (pure mode)."""
    from ..common.env import env

    def find_value(vars, names):
        if len(names) > 1:
            head = names[0]
            if head in vars:
                _vars = vars[head]
                assert isinstance(_vars, dict)
                return find_value(_vars, names[1:])
        else:
            name = names[0]
            if name in vars:
                return vars[name]
        return None

    assert env.runtime_info is not None
    vars = env.runtime_info.global_vars
    names = [sym if isinstance(sym, str) else sym.name for sym in qsym]
    if qsym[0].scope.is_global():
        names = ["__main__"] + names
    elif qsym[0].scope.is_namespace() and not qsym[0].scope.is_global():
        names = [qsym[0].scope.name] + names
    v = find_value(vars, names)
    if isinstance(v, dict) and not v:
        return None
    if v is not None:
        return expr2ir(v, scope=scope)
    return None


def try_get_constant(qsym: tuple[Symbol, ...], scope: Scope) -> IrExp | None:
    """Get constant value for a qualified symbol.

    In pure mode, looks up runtime global vars.
    Otherwise, looks up scope.constants table.
    Returns IR expression or None.
    """
    from ..common.env import env

    if env.config.enable_pure:
        return _try_get_constant_pure(qsym, scope)
    else:
        return _try_get_constant(qsym, scope)


def bits2int(bits: int, nbit: int) -> int:
    """Convert a bit pattern to a signed integer."""
    signbit = bits & (1 << (nbit - 1))
    if signbit:
        mask = (1 << nbit) - 1
        return -((bits ^ mask) + 1)
    else:
        return bits
