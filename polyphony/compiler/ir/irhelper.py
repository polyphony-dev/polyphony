from .ir import *
from .irvisitor import IRVisitor


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
        ar = ARRAY(items)
        ar.symbol = scope.add_temp('@array', {'predefined'})
        return ar
    elif isinstance(expr, tuple):
        items = [expr2ir(e) for e in expr]
        ar = ARRAY(items)
        ar.symbol = scope.add_temp('@array', {'predefined'})
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
            return TEMP(sym, Ctx.LOAD)
        elif inspect.isfunction(expr):
            fsym = scope.find_sym(name)
            assert fsym.typ.is_function()
            return TEMP(fsym, Ctx.LOAD)
        elif inspect.ismethod(expr):
            fsym = scope.find_sym(name)
            assert fsym.typ.is_function()
            return TEMP(fsym, Ctx.LOAD)
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


def is_port_method_call(call):
    if not call.is_a(CALL):
        return False
    calee_scope = call.callee_scope
    return (calee_scope.is_method() and
            calee_scope.parent.is_port())


def has_exclusive_function(stm):
    if stm.is_a(MOVE):
        call = stm.src
    elif stm.is_a(EXPR):
        call = stm.exp
    else:
        return False
    if is_port_method_call(call):
        if stm.block.synth_params['scheduling'] == 'timed':
            return False
        return True
    if has_clkfence(stm):
        return True
    return False


def has_clkfence(stm):
    if (stm.is_a(EXPR) and stm.exp.is_a(SYSCALL) and
            stm.exp.symbol.name == 'polyphony.timing.clksleep'):
        return True
    elif (stm.is_a(EXPR) and stm.exp.is_a(SYSCALL) and
            stm.exp.symbol.name.startswith('polyphony.timing.wait_')):
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
