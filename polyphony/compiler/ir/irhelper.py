from __future__ import annotations
from typing import TYPE_CHECKING
from .ir import *
from .irvisitor import IRVisitor
from .symbol import Symbol
from .types.type import Type
from .types.scopetype import ScopeType
if TYPE_CHECKING:
    from .scope import Scope


def op2str(op):
    return op.__class__.__name__


def expr2ir(expr, name=None, scope=None):
    import inspect
    from ..common.env import env
    from .types.type import Type
    if expr is None:
        return CONST(None)
    elif isinstance(expr, int):
        return CONST(expr)
    elif isinstance(expr, str):
        return CONST(expr)
    elif isinstance(expr, list):
        items = [expr2ir(e) for e in expr]
        ar = ARRAY(items, mutable=True)
        return ar
    elif isinstance(expr, tuple):
        items = [expr2ir(e) for e in expr]
        ar = ARRAY(items, mutable=False)
        return ar
    else:
        if inspect.isclass(expr):
            if expr.__module__ == 'polyphony.typing':
                klass_name = expr.__module__ + '.' + expr.__name__
                klass_scope = env.scopes[klass_name]
                t = Type.klass(klass_scope)
                sym = scope.add_temp('@dtype', {'predefined'})
                sym.typ = t
            elif expr.__module__ == 'builtins':
                klass_name = '__builtin__.' + expr.__name__
                klass_scope = env.scopes[klass_name]
                t = Type.klass(klass_scope)
                sym = scope.add_temp('@dtype', {'predefined'})
                sym.typ = t
            else:
                assert False
            return TEMP(sym.name)
        elif inspect.isfunction(expr):
            fsym = scope.find_sym(name)
            assert fsym.typ.is_function()
            return TEMP(name)
        elif inspect.ismethod(expr):
            fsym = scope.find_sym(name)
            assert fsym.typ.is_function()
            return TEMP(name)
        assert False


def reduce_relexp(exp):
    if exp.is_a(RELOP):
        if exp.op == 'And':
            exp.left = reduce_relexp(exp.left)
            exp.right = reduce_relexp(exp.right)
            if exp.left.is_a(CONST):
                if exp.left.value:
                    return exp.right
                else:
                    return CONST(0)
            elif exp.left.is_a(UNOP) and exp.left.op == 'Not' and exp.left.exp.is_a(CONST):
                if exp.left.exp.value:
                    return CONST(0)
                else:
                    return exp.right
            elif exp.right.is_a(CONST):
                if exp.right.value:
                    return exp.left
                else:
                    return CONST(0)
            elif exp.right.is_a(UNOP) and exp.right.op == 'Not' and exp.right.exp.is_a(CONST):
                if exp.right.exp.value:
                    return CONST(0)
                else:
                    return exp.left
        elif exp.op == 'Or':
            exp.left = reduce_relexp(exp.left)
            exp.right = reduce_relexp(exp.right)
            if exp.left.is_a(CONST):
                if exp.left.value:
                    return CONST(1)
                else:
                    return exp.right
            elif exp.left.is_a(UNOP) and exp.left.op == 'Not' and exp.left.exp.is_a(CONST):
                if exp.left.exp.value:
                    return exp.right
                else:
                    return CONST(1)
            elif exp.right.is_a(CONST):
                if exp.right.value:
                    return CONST(1)
                else:
                    return exp.left
            elif exp.right.is_a(UNOP) and exp.right.op == 'Not' and exp.right.exp.is_a(CONST):
                if exp.right.exp.value:
                    return exp.left
                else:
                    return CONST(1)
    elif exp.is_a(UNOP) and exp.op == 'Not':
        nexp = reduce_relexp(exp.exp)
        if nexp.is_a(CONST):
            if nexp.value:
                return CONST(0)
            else:
                return CONST(1)
        else:
            return UNOP('Not', nexp)
    return exp


def is_port_method_call(call, scope):
    if not call.is_a(CALL):
        return False
    calee_scope = call.get_callee_scope(scope)
    # calee_scope = call.callee_scope
    return (calee_scope.is_method() and
            calee_scope.parent.is_port())


def has_exclusive_function(stm, scope):
    if stm.is_a(MOVE):
        call = stm.src
    elif stm.is_a(EXPR):
        call = stm.exp
    else:
        return False
    if is_port_method_call(call, scope):
        if stm.block.synth_params['scheduling'] == 'timed':
            return False
        return True
    if has_clkfence(stm):
        return True
    return False


def has_clkfence(stm):
    if (stm.is_a(EXPR) and stm.exp.is_a(SYSCALL) and
            stm.exp.name == 'polyphony.timing.clksleep'):
        return True
    elif (stm.is_a(EXPR) and stm.exp.is_a(SYSCALL) and
            stm.exp.name.startswith('polyphony.timing.wait_')):
        return True
    else:
        return False


def eval_unop(op, v):
    if op == 'Invert':
        return ~v
    elif op == 'Not':
        return 1 if (not v) is True else 0
    elif op == 'UAdd':
        return v
    elif op == 'USub':
        return -v
    else:
        return None


def eval_binop(op, lv, rv):
    if op == 'Add':
        return lv + rv
    elif op == 'Sub':
        return lv - rv
    elif op == 'Mult':
        return lv * rv
    elif op == 'FloorDiv':
        return lv // rv
    elif op == 'Mod':
        return lv % rv
    elif op == 'Mod':
        return lv % rv
    elif op == 'LShift':
        return lv << rv
    elif op == 'RShift':
        return lv >> rv
    elif op == 'BitOr':
        return lv | rv
    elif op == 'BitXor':
        return lv ^ rv
    elif op == 'BitAnd':
        return lv & rv
    else:
        return None


def reduce_binop(ir):
    op = ir.op
    if ir.left.is_a(CONST):
        const = ir.left.value
        var = ir.right
    elif ir.right.is_a(CONST):
        const = ir.right.value
        var = ir.left
    else:
        assert False
    if op == 'Add' and const == 0:
        return var
    elif op == 'Mult' and const == 1:
        return var
    elif op == 'Mult' and const == 0:
        return CONST(0)
    return ir


def eval_relop(op, lv, rv):
    if op == 'Eq':
        b = lv == rv
    elif op == 'NotEq':
        b = lv != rv
    elif op == 'Lt':
        b = lv < rv
    elif op == 'LtE':
        b = lv <= rv
    elif op == 'Gt':
        b = lv > rv
    elif op == 'GtE':
        b = lv >= rv
    elif op == 'Is':
        b = lv is rv
    elif op == 'IsNot':
        b = lv is not rv
    elif op == 'And':
        b = lv and rv
    elif op == 'Or':
        b = lv or rv
    else:
        return None
    return 1 if b else 0


def find_move_src(sym, typ):
    scope = sym.scope
    if scope.is_class():
        scope = scope.find_ctor()
    finder = StmFinder(sym)
    finder.process(scope)
    for stm in finder.results:
        if stm.is_a(MOVE) and stm.src.is_a(typ):
            return stm.src
    return None


def qualified_symbols(ir: IRNameExp, scope: Scope) -> tuple[Symbol|str, ...]:
    assert isinstance(ir, IRNameExp)
    qname = ir.qualified_name
    symbol_or_names:list[Symbol|str] = []
    for i, name in enumerate(qname):
        symbol = scope.find_sym(name)
        if symbol:
            assert isinstance(symbol, Symbol)
            symbol_or_names.append(symbol)
            if symbol.typ.has_scope():
                scope = cast(ScopeType, symbol.typ).scope
            else:
                symbol_or_names.extend(qname[i+1:])
                break
        else:
            symbol_or_names.extend(qname[i:])
            break
    assert len(symbol_or_names) == len(qname)
    return tuple(symbol_or_names)


def qsym2var(qsym: tuple[Symbol,...], ctx: Ctx) -> IRVariable:
    assert len(qsym) > 0
    exp = TEMP(qsym[0].name)
    for sym in qsym[1:]:
        exp = ATTR(exp, sym.name)
    exp._ctx = ctx
    return exp


def irexp_type(ir: IRExp, scope: Scope) -> Type:
    assert isinstance(ir, IRExp)
    match ir:
        case ARRAY() as array:
            if array.items:
                elm_typ = irexp_type(array.items[0], scope)
            else:
                elm_typ = Type.none()
            if array.repeat.is_a(CONST):
                length = len(array.items) * array.repeat.value
            else:
                length = Type.ANY_LENGTH
            if array.is_mutable:
                return Type.list(elm_typ, length)
            else:
                return Type.tuple(elm_typ, length)
        case IRNameExp() as ir:
            qsym = qualified_symbols(ir, scope)
            assert isinstance(qsym[-1], Symbol)
            return qsym[-1].typ
        case MREF() as mref:
            return irexp_type(mref.mem, scope)
        case BINOP() as binop:
            return irexp_type(binop.left, scope)
        case RELOP():
            return Type.bool()
        case UNOP() as unop:
            return irexp_type(unop.exp, scope)
        case CONST():
            return Type.int()
        case _:
            assert False


class StmFinder(IRVisitor):
    def __init__(self, target_sym):
        self.target_sym = target_sym
        self.results = []

    def visit_ATTR(self, ir):
        if ir.symbol is self.target_sym:
            self.results.append(self.current_stm)

    def visit_TEMP(self, ir):
        if ir.symbol is self.target_sym:
            self.results.append(self.current_stm)
