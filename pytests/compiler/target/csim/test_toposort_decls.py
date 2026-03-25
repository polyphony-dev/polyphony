"""Tests for topological sorting of AHDL declarations."""
from unittest.mock import MagicMock
from polyphony.compiler.ahdl.ahdl import (
    AHDL_ASSIGN, AHDL_VAR, Ctx,
)
from polyphony.compiler.target.csim.csimgen import toposort_decls


def _make_signal(name, width=8, tags=None):
    sig = MagicMock()
    sig.name = name
    sig.width = width
    sig.tags = set(tags or {'net'})
    sig.is_reg = lambda: 'reg' in sig.tags
    sig.is_net = lambda: 'net' in sig.tags
    sig.is_regarray = lambda: 'regarray' in sig.tags
    sig.is_netarray = lambda: 'netarray' in sig.tags
    sig.is_constant = lambda: 'constant' in sig.tags
    sig.is_rom = lambda: 'rom' in sig.tags
    sig.is_int = lambda: 'int' in sig.tags
    sig.is_input = lambda: 'input' in sig.tags
    sig.is_output = lambda: 'output' in sig.tags
    sig.__eq__ = lambda self, other: self.name == other.name
    sig.__hash__ = lambda self: hash(self.name)
    return sig


def _make_assign(dst_name, src_names):
    """Create an AHDL_ASSIGN: dst := op(src1, src2, ...)
    For simplicity, if single src, use AHDL_VAR; otherwise chain isn't needed
    since toposort only cares about signal names in dst/src.
    """
    dst = AHDL_VAR((_make_signal(dst_name),), Ctx.STORE)
    if len(src_names) == 1:
        src = AHDL_VAR((_make_signal(src_names[0]),), Ctx.LOAD)
    else:
        # Use AHDL_OP for multi-source
        from polyphony.compiler.ahdl.ahdl import AHDL_OP
        args = [AHDL_VAR((_make_signal(n),), Ctx.LOAD) for n in src_names]
        src = AHDL_OP('Add', *args)
    return AHDL_ASSIGN(dst, src)


# --- Tests ---

def test_empty_decls():
    """Empty list returns empty list."""
    assert toposort_decls([]) == []


def test_single_decl():
    """Single decl returns unchanged."""
    d = _make_assign('a', ['x'])
    result = toposort_decls([d])
    assert result == [d]


def test_independent_decls_preserve_order():
    """Decls with no dependencies preserve original order."""
    d0 = _make_assign('a', ['x'])
    d1 = _make_assign('b', ['y'])
    result = toposort_decls([d0, d1])
    assert result == [d0, d1]


def test_linear_chain_reordered():
    """b := a, a := x  →  a := x, b := a (producer before consumer)."""
    d_b = _make_assign('b', ['a'])  # b depends on a
    d_a = _make_assign('a', ['x'])  # a depends on external x
    result = toposort_decls([d_b, d_a])
    assert result == [d_a, d_b]


def test_diamond_dependency():
    """d := b+c, b := a, c := a, a := x  →  a before b,c before d."""
    d_d = _make_assign('d', ['b', 'c'])
    d_b = _make_assign('b', ['a'])
    d_c = _make_assign('c', ['a'])
    d_a = _make_assign('a', ['x'])
    result = toposort_decls([d_d, d_b, d_c, d_a])
    # a must come first
    assert result.index(d_a) < result.index(d_b)
    assert result.index(d_a) < result.index(d_c)
    # b and c must come before d
    assert result.index(d_b) < result.index(d_d)
    assert result.index(d_c) < result.index(d_d)


def test_cycle_returns_all_decls():
    """Cyclic dependencies: a := b, b := a. All decls must be present."""
    d_a = _make_assign('a', ['b'])
    d_b = _make_assign('b', ['a'])
    result = toposort_decls([d_a, d_b])
    assert len(result) == 2
    assert set(result) == {d_a, d_b}


def test_cycle_preserves_original_order():
    """Cycle members appear in their original order."""
    d_a = _make_assign('a', ['b'])
    d_b = _make_assign('b', ['a'])
    result = toposort_decls([d_a, d_b])
    # Both have in-degree 1, so both go to remaining; original order preserved
    assert result == [d_a, d_b]


def test_mixed_dag_and_cycle():
    """DAG nodes are sorted; cycle members come after their DAG dependencies.
    x := ext, a := x+b, b := a  (a<->b cycle, x is DAG)
    """
    d_x = _make_assign('x', ['ext'])
    d_a = _make_assign('a', ['x', 'b'])
    d_b = _make_assign('b', ['a'])
    result = toposort_decls([d_b, d_a, d_x])
    # x has no internal deps -> comes first
    assert result.index(d_x) < result.index(d_a)
    assert result.index(d_x) < result.index(d_b)
    assert len(result) == 3


def test_generate_uses_toposort_for_decls():
    """generate() should emit decls in topological order within module_eval_decls."""
    from polyphony.compiler.target.csim.csimgen import AHDLToCTranspiler

    # Create signals: b := a, a := const(1)
    sig_a = _make_signal('a', 8, {'net'})
    sig_b = _make_signal('b', 8, {'net'})

    decl_b = AHDL_ASSIGN(
        AHDL_VAR((sig_b,), Ctx.STORE),
        AHDL_VAR((sig_a,), Ctx.LOAD),
    )
    from polyphony.compiler.ahdl.ahdl import AHDL_CONST
    decl_a = AHDL_ASSIGN(
        AHDL_VAR((sig_a,), Ctx.STORE),
        AHDL_CONST(42),
    )

    # Build a minimal hdlscope with decls in "wrong" order: b before a
    scope = MagicMock()
    scope.get_signals = lambda include_tags=None, exclude_tags=None: (
        [s for s in [sig_a, sig_b]
         if (not include_tags or include_tags & s.tags)
         and (not exclude_tags or not (exclude_tags & s.tags))]
    )
    scope.constants = {}
    scope.subscopes = {}
    scope.tasks = []
    scope.decls = [decl_b, decl_a]  # "wrong" order
    scope.functions = []

    tp = AHDLToCTranspiler()
    c_source, _, _, _ = tp.generate(scope)

    # In the generated C, the assignment to 'a' (s[S_a] = ..42..)
    # must appear before the assignment to 'b' (s[S_b] = ..s[S_a]..)
    lines = c_source.split('\n')
    assign_a_line = None
    assign_b_line = None
    for i, line in enumerate(lines):
        if 's[S_a]' in line and '42' in line:
            assign_a_line = i
        if 's[S_b]' in line and 's[S_a]' in line:
            assign_b_line = i
    assert assign_a_line is not None, f"Assignment to a not found in:\n{c_source}"
    assert assign_b_line is not None, f"Assignment to b not found in:\n{c_source}"
    assert assign_a_line < assign_b_line, (
        f"a (line {assign_a_line}) should come before b (line {assign_b_line})"
    )


def test_comb_def_use_collection():
    """AHDL_COMB with inner AHDL_ASSIGN stms should be analyzed for dependencies."""
    from polyphony.compiler.target.csim.csimgen import _collect_def_use
    from polyphony.compiler.ahdl.ahdl import AHDL_COMB

    inner_assign = AHDL_ASSIGN(
        AHDL_VAR((_make_signal('out'),), Ctx.STORE),
        AHDL_VAR((_make_signal('in1'),), Ctx.LOAD),
    )
    comb = AHDL_COMB('test_comb', (inner_assign,))
    defined, used = _collect_def_use(comb)
    assert 'out' in defined
    assert 'in1' in used


def test_comb_reordered_by_toposort():
    """AHDL_COMB that uses a signal defined by an AHDL_ASSIGN should come after it."""
    from polyphony.compiler.ahdl.ahdl import AHDL_COMB

    # assign: a := ext
    d_a = _make_assign('a', ['ext'])
    # comb: b := a (inside comb block)
    inner = AHDL_ASSIGN(
        AHDL_VAR((_make_signal('b'),), Ctx.STORE),
        AHDL_VAR((_make_signal('a'),), Ctx.LOAD),
    )
    d_comb = AHDL_COMB('comb1', (inner,))

    result = toposort_decls([d_comb, d_a])
    assert result.index(d_a) < result.index(d_comb)


def test_comb_with_if_block():
    """AHDL_COMB containing AHDL_IF with nested assigns should be analyzed."""
    from polyphony.compiler.target.csim.csimgen import _collect_def_use
    from polyphony.compiler.ahdl.ahdl import AHDL_COMB, AHDL_IF, AHDL_BLOCK

    assign_then = AHDL_ASSIGN(
        AHDL_VAR((_make_signal('out'),), Ctx.STORE),
        AHDL_VAR((_make_signal('in1'),), Ctx.LOAD),
    )
    assign_else = AHDL_ASSIGN(
        AHDL_VAR((_make_signal('out'),), Ctx.STORE),
        AHDL_VAR((_make_signal('in2'),), Ctx.LOAD),
    )
    cond = AHDL_VAR((_make_signal('sel'),), Ctx.LOAD)
    if_stm = AHDL_IF(
        (cond, None),
        (AHDL_BLOCK('then', (assign_then,)), AHDL_BLOCK('else', (assign_else,))),
    )
    comb = AHDL_COMB('mux', (if_stm,))
    defined, used = _collect_def_use(comb)
    assert 'out' in defined
    assert 'in1' in used
    assert 'in2' in used
    assert 'sel' in used
