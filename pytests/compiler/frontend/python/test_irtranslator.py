import types
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir import ir as new
from polyphony.compiler.ir.irhelper import irexp_type
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.frontend.python.irtranslator import IRTranslator
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def test_parse_expr():
    setup_test()
    src = '''
from polyphony.typing import List
List[0][1]
'''
    IRTranslator().translate(src, '')
    assert env.global_scope_name in env.scopes
    top = env.scopes[env.global_scope_name]
    stm = top.entry_block.stms[0]
    assert isinstance(stm, Expr)
    assert isinstance(stm.exp, MRef)
    mref = stm.exp
    assert isinstance(mref.mem, MRef)
    assert isinstance(mref.offset, Const)
    assert mref.offset.value == 1
    mref = mref.mem

    list_var = mref.mem
    assert isinstance(list_var, Temp)
    assert list_var.name == 'List'
    list_t = irexp_type(list_var, top)
    assert list_t.is_class()
    list_class = list_t.scope
    assert list_class.is_typeclass()

    assert isinstance(mref.offset, Const)
    assert mref.offset.value == 0

def test_parse_function_params():
    setup_test()
    src = '''
def f(a, b=10, c=20):
    pass
'''
    IRTranslator().translate(src, '')
    scope = env.scopes['@top.f']

    syms = scope.param_symbols()
    assert len(syms) == 3
    assert syms[0].name == '@in_a'
    assert syms[1].name == '@in_b'
    assert syms[2].name == '@in_c'

    vals = scope.param_default_values()
    assert len(vals) == 3
    assert vals[0] == None
    assert isinstance(vals[1], Const) and vals[1].value == 10
    assert isinstance(vals[2], Const) and vals[2].value == 20

def test_parse_class_params():
    setup_test()
    src = '''
class C:
    def __init__(self, a, b=123):
        self.a = a
        self.b = b
'''
    IRTranslator().translate(src, '')
    scope = env.scopes['@top.C.__init__']
    syms = scope.param_symbols(with_self=True)
    assert len(syms) == 3
    assert syms[0].name == '@in_self'
    assert syms[1].name == '@in_a'
    assert syms[2].name == '@in_b'
    syms = scope.param_symbols(with_self=False)
    assert len(syms) == 2
    assert syms[0].name == '@in_a'
    assert syms[1].name == '@in_b'

    vals = scope.param_default_values()
    assert len(vals) == 2
    assert vals[0] == None
    assert isinstance(vals[1], Const) and vals[1].value == 123

def test_parse_class_noparams():
    setup_test()
    src = '''
class D:
    pass
'''
    IRTranslator().translate(src, '')
    D = env.scopes['@top.D']
    ctor = env.scopes['@top.D.__init__']
    ctor_sym = D.find_sym('__init__')
    assert ctor_sym
    assert ctor_sym.typ.is_function()
    assert ctor_sym.typ.scope is ctor

    syms = ctor.param_symbols(with_self=True)
    assert len(syms) == 1
    assert syms[0].name == '@in_self'
    assert syms[0].is_self()


# ---- helpers ----
def _translate(src):
    """Translate source and return the top scope."""
    IRTranslator().translate(src, '')
    return env.scopes[env.global_scope_name]


def _collect_stms(scope):
    """Collect all statements from all blocks in a scope."""
    stms = []
    for blk in scope.traverse_blocks():
        stms.extend(blk.stms)
    return stms


# ============================================================
# Additional tests for coverage
# ============================================================


def test_return_statement():
    setup_test()
    src = '''
def f(x):
    return x
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    assert scope.is_returnable()
    stms = _collect_stms(scope)
    # Should have: mv x @in_x, mv @return x, jump(E) to exit, then ret
    moves = [s for s in stms if isinstance(s, Move)]
    jumps = [s for s in stms if isinstance(s, Jump)]
    assert any(isinstance(j, Jump) and j.typ == 'E' for j in jumps)


def test_if_statement():
    setup_test()
    src = '''
def f(x):
    if x:
        y = 1
    else:
        y = 2
    return y
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    cjumps = [s for s in stms if isinstance(s, CJump)]
    assert len(cjumps) >= 1


def test_if_elif():
    setup_test()
    src = '''
def f(x):
    if x:
        y = 1
    elif x:
        y = 2
    else:
        y = 3
    return y
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    cjumps = [s for s in stms if isinstance(s, CJump)]
    assert len(cjumps) >= 2


def test_while_loop():
    setup_test()
    src = '''
def f():
    i = 0
    while i < 10:
        i = i + 1
    return i
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    cjumps = [s for s in stms if isinstance(s, CJump)]
    assert len(cjumps) >= 1
    # Should have loop_branch set
    assert any(cj.loop_branch for cj in cjumps)
    # Should have a loop jump (typ='L')
    jumps = [s for s in stms if isinstance(s, Jump)]
    assert any(j.typ == 'L' for j in jumps)


def test_for_range_1arg():
    setup_test()
    src = '''
def f():
    s = 0
    for i in range(10):
        s = s + i
    return s
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    cjumps = [s for s in stms if isinstance(s, CJump)]
    assert len(cjumps) >= 1


def test_for_range_2arg():
    setup_test()
    src = '''
def f():
    s = 0
    for i in range(1, 10):
        s = s + i
    return s
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    cjumps = [s for s in stms if isinstance(s, CJump)]
    assert len(cjumps) >= 1


def test_for_range_3arg():
    setup_test()
    src = '''
def f():
    s = 0
    for i in range(0, 10, 2):
        s = s + i
    return s
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    cjumps = [s for s in stms if isinstance(s, CJump)]
    assert len(cjumps) >= 1


def test_for_over_variable():
    """for loop iterating over a variable (list) generates counter-based loop."""
    setup_test()
    src = '''
def f(lst):
    s = 0
    for x in lst:
        s = s + x
    return s
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    cjumps = [s for s in stms if isinstance(s, CJump)]
    assert len(cjumps) >= 1


def test_for_over_tuple_literal():
    """for loop iterating over a tuple literal like (1,2,3)."""
    setup_test()
    src = '''
def f():
    s = 0
    for x in (1, 2, 3):
        s = s + x
    return s
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    cjumps = [s for s in stms if isinstance(s, CJump)]
    assert len(cjumps) >= 1


def test_break_continue():
    setup_test()
    src = '''
def f():
    i = 0
    while i < 10:
        i = i + 1
        if i == 5:
            break
        if i == 3:
            continue
    return i
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    jumps = [s for s in stms if isinstance(s, Jump)]
    # Should have break jump (typ='B') and loop jump
    assert any(j.typ == 'B' for j in jumps)


def test_binop_const_fold():
    setup_test()
    src = '''
x = 3 + 4
'''
    top = _translate(src)
    stms = _collect_stms(top)
    moves = [s for s in stms if isinstance(s, Move)]
    # 3 + 4 should be folded to Const(7)
    assert any(isinstance(m.src, Const) and m.src.value == 7 for m in moves)


def test_unaryop():
    setup_test()
    src = '''
def f(x):
    return -x
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    moves = [s for s in stms if isinstance(s, Move)]
    # Should have a UnOp or Const
    assert any(isinstance(m.src, UnOp) for m in moves)


def test_unaryop_const_fold():
    setup_test()
    src = '''
x = -5
'''
    top = _translate(src)
    stms = _collect_stms(top)
    moves = [s for s in stms if isinstance(s, Move)]
    assert any(isinstance(m.src, Const) and m.src.value == -5 for m in moves)


def test_lambda():
    setup_test()
    src = '''
def f():
    g = lambda: 42
    return g
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    # lambda scope should exist (named @top.f.0, etc.)
    lambda_scopes = [s for name, s in env.scopes.items()
                     if name.startswith('@top.f.') and name != '@top.f']
    assert len(lambda_scopes) >= 1
    lscope = lambda_scopes[0]
    assert lscope.is_returnable()
    stms = _collect_stms(lscope)
    # Lambda body should have a Move and Ret
    assert any(isinstance(s, Ret) for s in stms)


def test_ifexp():
    setup_test()
    src = '''
def f(x):
    return 1 if x else 0
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    moves = [s for s in stms if isinstance(s, Move)]
    assert any(isinstance(m.src, CondOp) for m in moves)


def test_assert_statement():
    setup_test()
    src = '''
def f(x):
    assert x
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    exprs = [s for s in stms if isinstance(s, Expr)]
    assert any(isinstance(e.exp, SysCall) for e in exprs)


def test_list_literal():
    setup_test()
    src = '''
def f():
    x = [1, 2, 3]
    return x
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    moves = [s for s in stms if isinstance(s, Move)]
    assert any(isinstance(m.src, Array) and m.src.mutable for m in moves)


def test_tuple_literal():
    setup_test()
    src = '''
def f():
    x = (1, 2, 3)
    return x
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    moves = [s for s in stms if isinstance(s, Move)]
    assert any(isinstance(m.src, Array) and not m.src.mutable for m in moves)


def test_compare():
    setup_test()
    src = '''
def f(x, y):
    return x < y
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    moves = [s for s in stms if isinstance(s, Move)]
    assert any(isinstance(m.src, RelOp) for m in moves)


def test_compare_const_fold():
    setup_test()
    src = '''
x = 3 < 5
'''
    top = _translate(src)
    stms = _collect_stms(top)
    moves = [s for s in stms if isinstance(s, Move)]
    assert any(isinstance(m.src, Const) and m.src.value == True for m in moves)


def test_boolop():
    setup_test()
    src = '''
def f(x, y):
    return x and y
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    moves = [s for s in stms if isinstance(s, Move)]
    assert any(isinstance(m.src, RelOp) for m in moves)


def test_augassign_transform():
    """AugAssign (x += 1) should be transformed into x = x + 1."""
    setup_test()
    src = '''
def f(x):
    x += 1
    return x
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    moves = [s for s in stms if isinstance(s, Move)]
    assert any(isinstance(m.src, BinOp) and m.src.op == 'Add' for m in moves)


def test_compare_chain_transform():
    """Chained comparisons like a < b < c should be transformed."""
    setup_test()
    src = '''
def f(a, b, c):
    return a < b < c
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    moves = [s for s in stms if isinstance(s, Move)]
    # Should have a RelOp (from BoolOp(And, ...))
    assert any(isinstance(m.src, RelOp) for m in moves)


def test_ann_assign():
    """Annotated assignment like x: int = 5."""
    setup_test()
    src = '''
def f():
    x: int = 5
    return x
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    x_sym = scope.find_sym('x')
    assert x_sym is not None
    assert x_sym.typ.is_int()
    stms = _collect_stms(scope)
    moves = [s for s in stms if isinstance(s, Move)]
    assert any(isinstance(m.src, Const) and m.src.value == 5 for m in moves)


def test_function_return_annotation():
    """Function with return type annotation."""
    setup_test()
    src = '''
def f(x) -> int:
    return x
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    assert scope.return_type.is_int()
    assert scope.is_returnable()


def test_call_simple():
    setup_test()
    src = '''
def g(x):
    return x
def f():
    return g(1)
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    moves = [s for s in stms if isinstance(s, Move)]
    assert any(isinstance(m.src, Call) for m in moves)


def test_subscript():
    setup_test()
    src = '''
def f(x):
    return x[0]
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    moves = [s for s in stms if isinstance(s, Move)]
    assert any(isinstance(m.src, MRef) for m in moves)


def test_attribute_access():
    setup_test()
    src = '''
class C:
    def __init__(self):
        self.x = 0
    def get(self):
        return self.x
'''
    top = _translate(src)
    get_scope = env.scopes['@top.C.get']
    stms = _collect_stms(get_scope)
    moves = [s for s in stms if isinstance(s, Move)]
    assert any(isinstance(m.src, Attr) for m in moves)


def test_pass_statement():
    """Pass statement should generate no stms for body."""
    setup_test()
    src = '''
def f():
    pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    # Should still create scope without error
    assert scope is not None


def test_expr_statement():
    """Standalone expression statement."""
    setup_test()
    src = '''
def g():
    pass
def f():
    g()
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    exprs = [s for s in stms if isinstance(s, Expr)]
    assert len(exprs) >= 1


def test_new_class():
    """Creating a class instance should generate New node."""
    setup_test()
    src = '''
class C:
    def __init__(self, x):
        self.x = x
def f():
    c = C(1)
    return c
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    moves = [s for s in stms if isinstance(s, Move)]
    assert any(isinstance(m.src, New) for m in moves)


def test_name_constant_true_false_none():
    setup_test()
    src = '''
def f():
    a = True
    b = False
    c = None
    return a
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    moves = [s for s in stms if isinstance(s, Move)]
    consts = [m.src for m in moves if isinstance(m.src, Const)]
    values = [c.value for c in consts]
    assert True in values
    assert False in values
    assert None in values


def test_while_else():
    setup_test()
    src = '''
def f():
    i = 0
    while i < 5:
        i = i + 1
    else:
        i = -1
    return i
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    # Should have both while blocks and else block
    cjumps = [s for s in stms if isinstance(s, CJump)]
    assert len(cjumps) >= 1


def test_for_else():
    setup_test()
    src = '''
def f():
    s = 0
    for i in range(5):
        s = s + i
    else:
        s = -1
    return s
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    cjumps = [s for s in stms if isinstance(s, CJump)]
    assert len(cjumps) >= 1


def test_multiple_assign_targets():
    """x = y = 1 should produce two Move statements."""
    setup_test()
    src = '''
def f():
    x = y = 1
    return x
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    moves = [s for s in stms if isinstance(s, Move)]
    # Both x and y get assigned to 1
    const_moves = [m for m in moves if isinstance(m.src, Const) and m.src.value == 1]
    assert len(const_moves) >= 2


def test_call_with_kwargs():
    setup_test()
    src = '''
def g(x, y=10):
    return x
def f():
    return g(1, y=20)
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    moves = [s for s in stms if isinstance(s, Move)]
    calls = [m.src for m in moves if isinstance(m.src, Call)]
    assert len(calls) >= 1
    assert calls[0].kwargs.get('y') is not None



def test_nested_if_else():
    """Nested if-else should generate multiple CJump nodes."""
    setup_test()
    src = '''
def f(x, y):
    if x:
        if y:
            z = 1
        else:
            z = 2
    else:
        z = 3
    return z
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    cjumps = [s for s in stms if isinstance(s, CJump)]
    assert len(cjumps) >= 2


def test_class_with_multiple_methods():
    setup_test()
    src = '''
class C:
    def __init__(self, a, b):
        self.a = a
        self.b = b
    def add(self):
        return self.a + self.b
    def sub(self):
        return self.a - self.b
'''
    top = _translate(src)
    add_scope = env.scopes['@top.C.add']
    sub_scope = env.scopes['@top.C.sub']
    assert add_scope.is_returnable()
    assert sub_scope.is_returnable()


def test_function_calling_function():
    """Functions calling other functions."""
    setup_test()
    src = '''
def helper(x):
    return x + 1
def main(y):
    return helper(y)
'''
    top = _translate(src)
    main_scope = env.scopes['@top.main']
    stms = _collect_stms(main_scope)
    moves = [s for s in stms if isinstance(s, Move)]
    assert any(isinstance(m.src, Call) for m in moves)


def test_static_assignment():
    """Module-level assignment creates static symbol."""
    setup_test()
    src = '''
x = 42
'''
    top = _translate(src)
    x_sym = top.find_sym('x')
    assert x_sym is not None
    assert x_sym.is_static()


def test_class_static_var():
    """Class-level variable is marked static."""
    setup_test()
    src = '''
class C:
    x = 10
'''
    top = _translate(src)
    C = env.scopes['@top.C']
    x_sym = C.find_sym('x')
    assert x_sym is not None
    assert x_sym.is_static()


def test_subscript_store():
    """Subscript assignment (a[0] = val) generates MRef in dst."""
    setup_test()
    src = '''
def f():
    a = [0, 0]
    a[0] = 1
    return a
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    moves = [s for s in stms if isinstance(s, Move)]
    assert any(isinstance(m.dst, MRef) for m in moves)


def test_string_constant():
    setup_test()
    src = '''
x = "hello"
'''
    top = _translate(src)
    stms = _collect_stms(top)
    moves = [s for s in stms if isinstance(s, Move)]
    assert any(isinstance(m.src, Const) and m.src.value == "hello" for m in moves)


def test_boolop_or():
    setup_test()
    src = '''
def f(x, y):
    return x or y
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    moves = [s for s in stms if isinstance(s, Move)]
    assert any(isinstance(m.src, RelOp) for m in moves)


def test_multiple_returns():
    """Function with multiple return paths."""
    setup_test()
    src = '''
def f(x):
    if x:
        return 1
    return 0
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    ret_stms = [s for s in stms if isinstance(s, Ret)]
    assert len(ret_stms) >= 1


def test_method_attr_write_new():
    """Writing to self.new_attr creates a new symbol in class scope."""
    setup_test()
    src = '''
class C:
    def __init__(self):
        self.a = 1
        self.b = 2
'''
    top = _translate(src)
    C = env.scopes['@top.C']
    assert C.find_sym('a') is not None
    assert C.find_sym('b') is not None


def test_while_non_relop_condition():
    """While with a non-relop condition wraps in RelOp(NotEq, ..., 0)."""
    setup_test()
    src = '''
def f(x):
    while x:
        x = x - 1
    return x
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    cjumps = [s for s in stms if isinstance(s, CJump)]
    assert len(cjumps) >= 1
    # The condition should be wrapped in a RelOp(NotEq)
    cj = cjumps[0]
    assert isinstance(cj.exp, RelOp)


def test_if_constant_condition():
    """If with constant condition should still generate code."""
    setup_test()
    src = '''
def f():
    if True:
        x = 1
    else:
        x = 2
    return x
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    # Should have CJump even with constant (optimization happens later)
    cjumps = [s for s in stms if isinstance(s, CJump)]
    assert len(cjumps) >= 1

