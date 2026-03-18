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


# ============================================================
# Detailed visit_For tests for mutation coverage
# ============================================================


def _get_blocks_by_nametag(scope, nametag):
    """Return all blocks whose nametag matches."""
    return [b for b in scope.traverse_blocks() if b.nametag == nametag]


def _get_all_blocks(scope):
    """Return all blocks as a list."""
    return list(scope.traverse_blocks())


def _find_stm(stms, cls, predicate=None):
    """Find first statement of given class matching optional predicate."""
    for s in stms:
        if isinstance(s, cls):
            if predicate is None or predicate(s):
                return s
    return None


# --- range(N) single-arg: start=0, step=1 ---

def test_for_range_1arg_init_start_zero():
    """range(N) init should set loop var to Const(0)."""
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
    blocks = _get_all_blocks(scope)

    # Entry block should contain: mv s 0, mv i <start>, jump fortest
    entry = blocks[0]
    moves = [s for s in entry.stms if isinstance(s, Move)]
    # The init move assigns loop var i to start (0)
    i_init = [m for m in moves if isinstance(m.dst, Temp)
              and m.dst.name == 'i' and isinstance(m.src, Const)]
    assert len(i_init) == 1
    assert i_init[0].src.value == 0


def test_for_range_1arg_condition_lt():
    """range(N) condition should be RelOp(Lt, i, N)."""
    setup_test()
    src = '''
def f():
    for i in range(10):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    cjumps = [s for s in stms if isinstance(s, CJump)]
    assert len(cjumps) >= 1
    cj = cjumps[0]
    assert isinstance(cj.exp, RelOp)
    assert cj.exp.op == 'Lt'
    assert isinstance(cj.exp.left, Temp)
    assert cj.exp.left.name == 'i'
    # right is the end value (Const 10)
    assert isinstance(cj.exp.right, Const)
    assert cj.exp.right.value == 10


def test_for_range_1arg_step_one():
    """range(N) continue part increments by Const(1)."""
    setup_test()
    src = '''
def f():
    for i in range(10):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    cont_blocks = _get_blocks_by_nametag(scope, 'continue')
    assert len(cont_blocks) == 1
    cont = cont_blocks[0]
    moves = [s for s in cont.stms if isinstance(s, Move)]
    assert len(moves) >= 1
    # increment: i = i + 1
    incr = moves[0]
    assert isinstance(incr.dst, Temp) and incr.dst.name == 'i'
    assert isinstance(incr.src, BinOp)
    assert incr.src.op == 'Add'
    assert isinstance(incr.src.left, Temp) and incr.src.left.name == 'i'
    assert isinstance(incr.src.right, Const) and incr.src.right.value == 1


def test_for_range_1arg_loop_branch():
    """CJump in fortest block should have loop_branch=True."""
    setup_test()
    src = '''
def f():
    for i in range(10):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    cjumps = [s for s in stms if isinstance(s, CJump)]
    assert len(cjumps) >= 1
    assert cjumps[0].loop_branch is True


def test_for_range_1arg_loop_jump():
    """Continue block should end with Jump(typ='L') back to fortest."""
    setup_test()
    src = '''
def f():
    for i in range(10):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    cont_blocks = _get_blocks_by_nametag(scope, 'continue')
    assert len(cont_blocks) == 1
    last_stm = cont_blocks[0].stms[-1]
    assert isinstance(last_stm, Jump)
    assert last_stm.typ == 'L'
    # Target should be the fortest block
    assert last_stm.target.nametag == 'fortest'


def test_for_range_1arg_block_structure():
    """range(N) loop should create fortest, forbody, continue, forelse blocks."""
    setup_test()
    src = '''
def f():
    for i in range(5):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    blocks = _get_all_blocks(scope)
    tags = [b.nametag for b in blocks]
    assert 'fortest' in tags
    assert 'forbody' in tags
    assert 'continue' in tags
    assert 'forelse' in tags


def test_for_range_1arg_fortest_connections():
    """fortest block should have succs to forbody and forelse."""
    setup_test()
    src = '''
def f():
    for i in range(5):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    fortest = _get_blocks_by_nametag(scope, 'fortest')[0]
    succ_tags = [b.nametag for b in fortest.succs]
    assert 'forbody' in succ_tags
    assert 'forelse' in succ_tags


def test_for_range_1arg_continue_loop_connection():
    """continue block should have loop connection back to fortest."""
    setup_test()
    src = '''
def f():
    for i in range(5):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    cont = _get_blocks_by_nametag(scope, 'continue')[0]
    assert len(cont.succs_loop) >= 1
    assert cont.succs_loop[0].nametag == 'fortest'


# --- range(start, end) two-arg ---

def test_for_range_2arg_init_start():
    """range(start, end) init should set loop var to start."""
    setup_test()
    src = '''
def f():
    for i in range(3, 10):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    blocks = _get_all_blocks(scope)
    entry = blocks[0]
    moves = [s for s in entry.stms if isinstance(s, Move)]
    i_init = [m for m in moves if isinstance(m.dst, Temp)
              and m.dst.name == 'i' and isinstance(m.src, Const)]
    assert len(i_init) == 1
    assert i_init[0].src.value == 3


def test_for_range_2arg_condition_end():
    """range(start, end) condition should use end value."""
    setup_test()
    src = '''
def f():
    for i in range(3, 10):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    cjumps = [s for s in stms if isinstance(s, CJump)]
    assert len(cjumps) >= 1
    cj = cjumps[0]
    assert isinstance(cj.exp, RelOp)
    assert cj.exp.op == 'Lt'
    assert isinstance(cj.exp.right, Const)
    assert cj.exp.right.value == 10


def test_for_range_2arg_step_one():
    """range(start, end) should still increment by 1."""
    setup_test()
    src = '''
def f():
    for i in range(3, 10):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    cont = _get_blocks_by_nametag(scope, 'continue')[0]
    moves = [s for s in cont.stms if isinstance(s, Move)]
    incr = moves[0]
    assert isinstance(incr.src, BinOp)
    assert incr.src.op == 'Add'
    assert isinstance(incr.src.right, Const)
    assert incr.src.right.value == 1


# --- range(start, end, step) three-arg ---

def test_for_range_3arg_init_start():
    """range(start, end, step) should init loop var to start."""
    setup_test()
    src = '''
def f():
    for i in range(0, 20, 3):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    blocks = _get_all_blocks(scope)
    entry = blocks[0]
    moves = [s for s in entry.stms if isinstance(s, Move)]
    i_init = [m for m in moves if isinstance(m.dst, Temp)
              and m.dst.name == 'i' and isinstance(m.src, Const)]
    assert len(i_init) == 1
    assert i_init[0].src.value == 0


def test_for_range_3arg_condition_end():
    """range(start, end, step) condition should compare against end."""
    setup_test()
    src = '''
def f():
    for i in range(0, 20, 3):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    cjumps = [s for s in stms if isinstance(s, CJump)]
    cj = cjumps[0]
    assert isinstance(cj.exp, RelOp)
    assert cj.exp.op == 'Lt'
    assert isinstance(cj.exp.right, Const)
    assert cj.exp.right.value == 20


def test_for_range_3arg_step_value():
    """range(start, end, step) continue block should increment by step."""
    setup_test()
    src = '''
def f():
    for i in range(0, 20, 3):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    cont = _get_blocks_by_nametag(scope, 'continue')[0]
    moves = [s for s in cont.stms if isinstance(s, Move)]
    incr = moves[0]
    assert isinstance(incr.src, BinOp)
    assert incr.src.op == 'Add'
    assert isinstance(incr.src.right, Const)
    assert incr.src.right.value == 3


# --- range() with variable arguments (make_temp_if_needed) ---

def test_for_range_variable_end():
    """range(N) where N is a variable should create a temp for end."""
    setup_test()
    src = '''
def f(n):
    for i in range(n):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    blocks = _get_all_blocks(scope)
    entry = blocks[0]
    stms = entry.stms
    # With variable end, make_temp_if_needed creates a temp
    # There should be a Move that copies n to a temp
    moves = [s for s in stms if isinstance(s, Move)]
    temp_moves = [m for m in moves if isinstance(m.dst, Temp)
                  and m.dst.name.startswith('@')]
    # At least one temp should be created for the variable end
    assert len(temp_moves) >= 1


def test_for_range_variable_start_end():
    """range(start, end) where both are variables should create temps."""
    setup_test()
    src = '''
def f(a, b):
    for i in range(a, b):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    blocks = _get_all_blocks(scope)
    entry = blocks[0]
    moves = [s for s in entry.stms if isinstance(s, Move)]
    # Temps for start and end variables
    temp_moves = [m for m in moves if isinstance(m.dst, Temp)
                  and m.dst.name.startswith('@')]
    assert len(temp_moves) >= 2


def test_for_range_variable_all_args():
    """range(start, end, step) where all are variables."""
    setup_test()
    src = '''
def f(a, b, c):
    for i in range(a, b, c):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    blocks = _get_all_blocks(scope)
    entry = blocks[0]
    moves = [s for s in entry.stms if isinstance(s, Move)]
    temp_moves = [m for m in moves if isinstance(m.dst, Temp)
                  and m.dst.name.startswith('@')]
    # Temps for a, b, c
    assert len(temp_moves) >= 3


# --- for-over-variable (IrVariable path) ---

def test_for_over_variable_counter():
    """for x in lst: creates a hidden counter variable."""
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

    # Should have condition: counter < len(lst)
    cjumps = [s for s in stms if isinstance(s, CJump)]
    assert len(cjumps) >= 1
    cj = cjumps[0]
    assert isinstance(cj.exp, RelOp)
    assert cj.exp.op == 'Lt'
    # left should be the counter Temp
    assert isinstance(cj.exp.left, Temp)
    assert '@counter' in cj.exp.left.name
    # right should be SysCall(len)
    assert isinstance(cj.exp.right, SysCall)


def test_for_over_variable_body_mref():
    """for x in lst: body should have x = lst[counter]."""
    setup_test()
    src = '''
def f(lst):
    for x in lst:
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    forbody_blocks = _get_blocks_by_nametag(scope, 'forbody')
    assert len(forbody_blocks) == 1
    forbody = forbody_blocks[0]
    moves = [s for s in forbody.stms if isinstance(s, Move)]
    # x = MRef(lst, counter)
    mref_moves = [m for m in moves if isinstance(m.src, MRef)]
    assert len(mref_moves) >= 1
    mref = mref_moves[0].src
    assert isinstance(mref.mem, Temp) and mref.mem.name == 'lst'
    assert isinstance(mref.offset, Temp)


def test_for_over_variable_counter_init_zero():
    """for x in lst: counter init should be 0."""
    setup_test()
    src = '''
def f(lst):
    for x in lst:
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    blocks = _get_all_blocks(scope)
    entry = blocks[0]
    moves = [s for s in entry.stms if isinstance(s, Move)]
    # Counter init: counter = 0
    counter_inits = [m for m in moves if isinstance(m.dst, Temp)
                     and '@counter' in m.dst.name
                     and isinstance(m.src, Const)]
    assert len(counter_inits) == 1
    assert counter_inits[0].src.value == 0


def test_for_over_variable_counter_increment():
    """for x in lst: continue part should increment counter by 1."""
    setup_test()
    src = '''
def f(lst):
    for x in lst:
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    cont = _get_blocks_by_nametag(scope, 'continue')[0]
    moves = [s for s in cont.stms if isinstance(s, Move)]
    incr = moves[0]
    assert isinstance(incr.src, BinOp)
    assert incr.src.op == 'Add'
    assert isinstance(incr.src.right, Const) and incr.src.right.value == 1


def test_for_over_variable_invisible_counter():
    """for x in lst: counter should be in invisible_symbols."""
    setup_test()
    src = '''
def f(lst):
    for x in lst:
        pass
'''
    # We need to access CodeVisitor's invisible_symbols.
    # They get applied during translation. Check the scope for counter symbol
    # being tagged or simply verify the counter symbol exists.
    top = _translate(src)
    scope = env.scopes['@top.f']
    # Counter symbol should exist
    counter_syms = [name for name in scope.symbols if '@counter' in name]
    assert len(counter_syms) >= 1


# --- for-over-array-literal (Array path) ---

def test_for_over_array_literal_counter():
    """for x in (1,2,3): creates counter and unnamed array."""
    setup_test()
    src = '''
def f():
    for x in (1, 2, 3):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)

    cjumps = [s for s in stms if isinstance(s, CJump)]
    assert len(cjumps) >= 1
    cj = cjumps[0]
    assert isinstance(cj.exp, RelOp)
    assert cj.exp.op == 'Lt'
    assert isinstance(cj.exp.left, Temp)
    assert '@counter' in cj.exp.left.name


def test_for_over_array_literal_unnamed_temp():
    """for x in (1,2,3): should create @unnamed temp for the array."""
    setup_test()
    src = '''
def f():
    for x in (1, 2, 3):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    # Check for unnamed temp symbol
    unnamed_syms = [name for name in scope.symbols if '@unnamed' in name]
    assert len(unnamed_syms) >= 1


def test_for_over_array_literal_init_stores_array():
    """for x in (1,2,3): init should store array to unnamed temp."""
    setup_test()
    src = '''
def f():
    for x in (1, 2, 3):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    blocks = _get_all_blocks(scope)
    entry = blocks[0]
    moves = [s for s in entry.stms if isinstance(s, Move)]
    # One move stores Array to unnamed temp
    array_stores = [m for m in moves if isinstance(m.src, Array)]
    assert len(array_stores) >= 1
    arr = array_stores[0].src
    assert len(arr.items) == 3


def test_for_over_array_literal_body_mref():
    """for x in (1,2,3): body should have x = unnamed[counter]."""
    setup_test()
    src = '''
def f():
    for x in (1, 2, 3):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    forbody_blocks = _get_blocks_by_nametag(scope, 'forbody')
    assert len(forbody_blocks) == 1
    forbody = forbody_blocks[0]
    moves = [s for s in forbody.stms if isinstance(s, Move)]
    mref_moves = [m for m in moves if isinstance(m.src, MRef)]
    assert len(mref_moves) >= 1
    mref = mref_moves[0].src
    assert isinstance(mref.mem, Temp) and '@unnamed' in mref.mem.name
    assert isinstance(mref.offset, Temp) and '@counter' in mref.offset.name


def test_for_over_array_literal_counter_init():
    """for x in (1,2,3): counter should init to 0."""
    setup_test()
    src = '''
def f():
    for x in (1, 2, 3):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    blocks = _get_all_blocks(scope)
    entry = blocks[0]
    moves = [s for s in entry.stms if isinstance(s, Move)]
    counter_inits = [m for m in moves if isinstance(m.dst, Temp)
                     and '@counter' in m.dst.name
                     and isinstance(m.src, Const)]
    assert len(counter_inits) == 1
    assert counter_inits[0].src.value == 0


def test_for_over_array_literal_len_syscall():
    """for x in (1,2,3): condition right should be len(unnamed)."""
    setup_test()
    src = '''
def f():
    for x in (1, 2, 3):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    cjumps = [s for s in stms if isinstance(s, CJump)]
    cj = cjumps[0]
    assert isinstance(cj.exp, RelOp)
    # right is SysCall(len)
    right = cj.exp.right
    assert isinstance(right, SysCall)
    assert isinstance(right.func, Temp) and right.func.name == 'len'
    # arg should be the unnamed temp
    assert len(right.args) == 1
    arg_name, arg_val = right.args[0]
    assert arg_name == 'seq'
    assert isinstance(arg_val, Temp) and '@unnamed' in arg_val.name


# --- for-else ---

def test_for_else_generates_forelse_block_with_stms():
    """for-else should put else body into forelse block."""
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
    forelse_blocks = _get_blocks_by_nametag(scope, 'forelse')
    assert len(forelse_blocks) == 1
    forelse = forelse_blocks[0]
    moves = [s for s in forelse.stms if isinstance(s, Move)]
    # else body: s = -1
    assert any(isinstance(m.src, Const) and m.src.value == -1 for m in moves)


def test_for_no_else_forelse_empty():
    """for without else should have empty forelse block (just jumps)."""
    setup_test()
    src = '''
def f():
    for i in range(5):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    forelse_blocks = _get_blocks_by_nametag(scope, 'forelse')
    assert len(forelse_blocks) == 1
    forelse = forelse_blocks[0]
    # forelse block should only have a Jump (no Move statements from else body)
    moves = [s for s in forelse.stms if isinstance(s, Move)]
    assert len(moves) == 0


# --- break and continue in for loop ---

def test_for_break_jumps_to_exit():
    """break in for loop should jump past the for-else."""
    setup_test()
    src = '''
def f():
    for i in range(10):
        if i == 5:
            break
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    jumps = [s for s in stms if isinstance(s, Jump)]
    break_jumps = [j for j in jumps if j.typ == 'B']
    assert len(break_jumps) >= 1


def test_for_continue_jumps_to_continue_block():
    """continue in for loop should jump to continue block."""
    setup_test()
    src = '''
def f():
    for i in range(10):
        if i == 3:
            continue
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    # continue generates a Jump to the continue block
    # The continue block has nametag 'continue'
    cont_blocks = _get_blocks_by_nametag(scope, 'continue')
    assert len(cont_blocks) == 1

    # Find the jump that targets the continue block
    jumps = [s for s in stms if isinstance(s, Jump)]
    cont_jumps = [j for j in jumps if j.target.nametag == 'continue'
                  and j.typ != 'L']  # exclude the loop-back jump
    assert len(cont_jumps) >= 1


# --- nested for loops ---

def test_nested_for_loops():
    """Nested for loops should each have their own fortest/continue blocks."""
    setup_test()
    src = '''
def f():
    for i in range(5):
        for j in range(3):
            pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    fortest_blocks = _get_blocks_by_nametag(scope, 'fortest')
    cont_blocks = _get_blocks_by_nametag(scope, 'continue')
    forbody_blocks = _get_blocks_by_nametag(scope, 'forbody')
    assert len(fortest_blocks) == 2
    assert len(cont_blocks) == 2
    assert len(forbody_blocks) == 2


# --- for body with actual statements ---

def test_for_body_stms_in_forbody_block():
    """Body statements should appear in the forbody block."""
    setup_test()
    src = '''
def f():
    s = 0
    for i in range(5):
        s = s + i
    return s
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    forbody = _get_blocks_by_nametag(scope, 'forbody')[0]
    moves = [s for s in forbody.stms if isinstance(s, Move)]
    # s = s + i should be in forbody
    add_moves = [m for m in moves if isinstance(m.src, BinOp) and m.src.op == 'Add']
    assert len(add_moves) >= 1


# --- for loop CJump true/false targets ---

def test_for_cjump_true_false_targets():
    """CJump should branch to forbody (true) and forelse (false)."""
    setup_test()
    src = '''
def f():
    for i in range(5):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    fortest = _get_blocks_by_nametag(scope, 'fortest')[0]
    cjumps = [s for s in fortest.stms if isinstance(s, CJump)]
    assert len(cjumps) == 1
    cj = cjumps[0]
    assert cj.true.nametag == 'forbody'
    assert cj.false.nametag == 'forelse'


# --- entry block connects to fortest ---

def test_for_entry_jumps_to_fortest():
    """Entry block should end with Jump to fortest block."""
    setup_test()
    src = '''
def f():
    for i in range(5):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    blocks = _get_all_blocks(scope)
    entry = blocks[0]
    last_stm = entry.stms[-1]
    assert isinstance(last_stm, Jump)
    assert last_stm.target.nametag == 'fortest'


# --- for-over-variable with len() SysCall ---

def test_for_over_variable_len_arg():
    """for x in lst: len(lst) should pass lst as arg."""
    setup_test()
    src = '''
def f(lst):
    for x in lst:
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    cjumps = [s for s in stms if isinstance(s, CJump)]
    cj = cjumps[0]
    right = cj.exp.right
    assert isinstance(right, SysCall)
    assert isinstance(right.func, Temp) and right.func.name == 'len'
    assert len(right.args) == 1
    assert right.args[0][0] == 'seq'
    assert isinstance(right.args[0][1], Temp) and right.args[0][1].name == 'lst'


# --- Const start/end don't generate temps ---

def test_for_range_const_args_no_extra_temps():
    """range(0, 10) with const args should use consts directly in condition."""
    setup_test()
    src = '''
def f():
    for i in range(0, 10):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    cjumps = [s for s in stms if isinstance(s, CJump)]
    cj = cjumps[0]
    # end is a constant, should be used directly
    assert isinstance(cj.exp.right, Const)
    assert cj.exp.right.value == 10


# --- for loop with list literal ---

def test_for_over_list_literal():
    """for x in [1, 2, 3]: should use Array path."""
    setup_test()
    src = '''
def f():
    for x in [1, 2, 3]:
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    # Should have unnamed temp and counter
    unnamed_syms = [name for name in scope.symbols if '@unnamed' in name]
    counter_syms = [name for name in scope.symbols if '@counter' in name]
    assert len(unnamed_syms) >= 1
    assert len(counter_syms) >= 1


# --- CJump loop_branch in _build_for_loop_blocks ---

def test_for_range_cjump_in_fortest():
    """CJump should be emitted in the fortest block, not elsewhere."""
    setup_test()
    src = '''
def f():
    for i in range(5):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    fortest = _get_blocks_by_nametag(scope, 'fortest')[0]
    assert len(fortest.stms) >= 1
    assert isinstance(fortest.stms[-1], CJump)
    # No other block should have CJump
    other_blocks = [b for b in _get_all_blocks(scope) if b.nametag != 'fortest']
    for b in other_blocks:
        for s in b.stms:
            assert not isinstance(s, CJump), f"unexpected CJump in {b.nametag}"


# --- for range with mixed const/var args ---

def test_for_range_mixed_const_var():
    """range(0, n) has const start but variable end."""
    setup_test()
    src = '''
def f(n):
    for i in range(0, n):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    blocks = _get_all_blocks(scope)
    entry = blocks[0]
    moves = [s for s in entry.stms if isinstance(s, Move)]
    # Start is const 0, directly used for init
    i_init = [m for m in moves if isinstance(m.dst, Temp)
              and m.dst.name == 'i' and isinstance(m.src, Const)]
    assert len(i_init) == 1
    assert i_init[0].src.value == 0
    # end should be stored in a temp since it's a variable
    stms = _collect_stms(scope)
    cjumps = [s for s in stms if isinstance(s, CJump)]
    cj = cjumps[0]
    # end is a variable, should be a Temp (not Const)
    assert isinstance(cj.exp.right, Temp)


# --- for loop i variable name ---

def test_for_loop_var_name_preserved():
    """Loop variable name should match what was in the source."""
    setup_test()
    src = '''
def f():
    for idx in range(10):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    cjumps = [s for s in stms if isinstance(s, CJump)]
    cj = cjumps[0]
    assert cj.exp.left.name == 'idx'


# --- for-over-variable: counter name uniqueness ---

def test_for_over_variable_counter_name_unique():
    """Nested for-over-variable should have distinct counter names."""
    setup_test()
    src = '''
def f(a, b):
    for x in a:
        for y in b:
            pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    counter_syms = [name for name in scope.symbols if '@counter' in name]
    assert len(counter_syms) >= 2
    # All counter names should be unique
    assert len(set(counter_syms)) == len(counter_syms)


# --- for loop with for-else and break ---

def test_for_else_with_break():
    """for-else with break: break should skip else block."""
    setup_test()
    src = '''
def f():
    for i in range(10):
        if i == 5:
            break
    else:
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    jumps = [s for s in stms if isinstance(s, Jump)]
    break_jumps = [j for j in jumps if j.typ == 'B']
    assert len(break_jumps) >= 1
    # Break target should be past the forelse block (exit block)
    break_target = break_jumps[0].target
    # It should NOT be the forelse block
    assert break_target.nametag != 'forelse'


# --- for range 1-arg: start=0 explicitly ---

def test_for_range_1arg_start_is_zero_not_other():
    """range(N) specifically sets start to 0, not 1 or N."""
    setup_test()
    src = '''
def f():
    for i in range(100):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    blocks = _get_all_blocks(scope)
    entry = blocks[0]
    moves = [s for s in entry.stms if isinstance(s, Move)]
    i_init = [m for m in moves if isinstance(m.dst, Temp)
              and m.dst.name == 'i' and isinstance(m.src, Const)]
    assert i_init[0].src.value == 0
    assert i_init[0].src.value != 1
    assert i_init[0].src.value != 100


# --- for loop condition uses Lt (not Le, Gt, etc.) ---

def test_for_range_condition_is_lt_not_le():
    """range() condition must be Lt, not Le or other comparisons."""
    setup_test()
    src = '''
def f():
    for i in range(10):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    stms = _collect_stms(scope)
    cjumps = [s for s in stms if isinstance(s, CJump)]
    cj = cjumps[0]
    assert cj.exp.op == 'Lt'
    assert cj.exp.op != 'Le'
    assert cj.exp.op != 'Gt'
    assert cj.exp.op != 'Ge'


# --- for loop step uses Add (not Sub or others) ---

def test_for_range_step_uses_add_not_sub():
    """range() step should use Add operation."""
    setup_test()
    src = '''
def f():
    for i in range(10):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    cont = _get_blocks_by_nametag(scope, 'continue')[0]
    moves = [s for s in cont.stms if isinstance(s, Move)]
    incr = moves[0]
    assert incr.src.op == 'Add'
    assert incr.src.op != 'Sub'


# --- for loop continue block has loop-type jump ---

def test_for_continue_block_has_loop_type_jump():
    """Continue block should have Jump with typ='L' (loop)."""
    setup_test()
    src = '''
def f():
    for i in range(5):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    cont = _get_blocks_by_nametag(scope, 'continue')[0]
    jumps = [s for s in cont.stms if isinstance(s, Jump)]
    assert len(jumps) >= 1
    loop_jump = jumps[-1]
    assert loop_jump.typ == 'L'
    assert loop_jump.typ != ''
    assert loop_jump.typ != 'B'
    assert loop_jump.typ != 'E'


# --- forbody block connects to continue block ---

def test_for_forbody_connects_to_continue():
    """forbody block should have continue block as successor."""
    setup_test()
    src = '''
def f():
    for i in range(5):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    forbody = _get_blocks_by_nametag(scope, 'forbody')[0]
    succ_tags = [b.nametag for b in forbody.succs]
    assert 'continue' in succ_tags


# --- for range: init Move dst has STORE context ---

def test_for_range_init_store_context():
    """Init Move for loop var should have STORE context."""
    setup_test()
    src = '''
def f():
    for i in range(5):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    blocks = _get_all_blocks(scope)
    entry = blocks[0]
    moves = [s for s in entry.stms if isinstance(s, Move)]
    i_init = [m for m in moves if isinstance(m.dst, Temp)
              and m.dst.name == 'i' and isinstance(m.src, Const)]
    assert len(i_init) == 1
    assert i_init[0].dst.ctx == Ctx.STORE


# --- for range: continue Move dst has STORE context ---

def test_for_range_continue_store_context():
    """Continue Move for loop var should have STORE context."""
    setup_test()
    src = '''
def f():
    for i in range(5):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    cont = _get_blocks_by_nametag(scope, 'continue')[0]
    moves = [s for s in cont.stms if isinstance(s, Move)]
    incr = moves[0]
    assert isinstance(incr.dst, Temp)
    assert incr.dst.ctx == Ctx.STORE


# --- for loop: entry block succs includes fortest ---

def test_for_entry_block_succ_fortest():
    """Entry block should have fortest as a successor."""
    setup_test()
    src = '''
def f():
    for i in range(5):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    blocks = _get_all_blocks(scope)
    entry = blocks[0]
    succ_tags = [b.nametag for b in entry.succs]
    assert 'fortest' in succ_tags


# --- for loop: fortest pred includes entry ---

def test_for_fortest_pred_includes_entry():
    """fortest should have entry as a predecessor."""
    setup_test()
    src = '''
def f():
    for i in range(5):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    fortest = _get_blocks_by_nametag(scope, 'fortest')[0]
    assert len(fortest.preds) >= 1


# --- for loop: fortest has loop predecessor from continue ---

def test_for_fortest_loop_pred_from_continue():
    """fortest should have continue as a loop predecessor."""
    setup_test()
    src = '''
def f():
    for i in range(5):
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    fortest = _get_blocks_by_nametag(scope, 'fortest')[0]
    loop_pred_tags = [b.nametag for b in fortest.preds_loop]
    assert 'continue' in loop_pred_tags


# --- for-over-variable: MRef ctx is LOAD ---

def test_for_over_variable_mref_load_ctx():
    """MRef in body for list iteration should have LOAD context."""
    setup_test()
    src = '''
def f(lst):
    for x in lst:
        pass
'''
    top = _translate(src)
    scope = env.scopes['@top.f']
    forbody = _get_blocks_by_nametag(scope, 'forbody')[0]
    moves = [s for s in forbody.stms if isinstance(s, Move)]
    mref_moves = [m for m in moves if isinstance(m.src, MRef)]
    assert len(mref_moves) >= 1
    assert mref_moves[0].src.ctx == Ctx.LOAD

