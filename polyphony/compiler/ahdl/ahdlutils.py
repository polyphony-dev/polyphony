from __future__ import annotations

from collections import defaultdict, deque

from .ahdl import (
    AHDL_ASSIGN,
    AHDL_BLOCK,
    AHDL_CASE,
    AHDL_CASE_ITEM,
    AHDL_COMB,
    AHDL_CONST,
    AHDL_FUNCALL,
    AHDL_IF,
    AHDL_IF_EXP,
    AHDL_MEMVAR,
    AHDL_MOVE,
    AHDL_OP,
    AHDL_SUBSCRIPT,
    AHDL_SYMBOL,
    AHDL_VAR,
)


def collect_sig_names(node, names: set[str]):
    """Recursively collect signal names from an AHDL expression tree."""
    if isinstance(node, AHDL_VAR):
        names.add(node.vars[-1].name)
    elif isinstance(node, AHDL_SUBSCRIPT):
        names.add(node.memvar.vars[-1].name)
        collect_sig_names(node.offset, names)
    elif isinstance(node, AHDL_MEMVAR):
        names.add(node.vars[-1].name)
    elif isinstance(node, AHDL_OP):
        for arg in node.args:
            collect_sig_names(arg, names)
    elif isinstance(node, AHDL_IF_EXP):
        collect_sig_names(node.cond, names)
        collect_sig_names(node.lexp, names)
        collect_sig_names(node.rexp, names)
    elif isinstance(node, AHDL_FUNCALL):
        for arg in node.args:
            collect_sig_names(arg, names)
    elif isinstance(node, (AHDL_CONST, AHDL_SYMBOL)):
        pass


def collect_def_use(decl) -> tuple[set[str], set[str]]:
    """Return (defined_signals, used_signals) for a single decl."""
    defined: set[str] = set()
    used: set[str] = set()
    if isinstance(decl, (AHDL_ASSIGN, AHDL_MOVE)):
        collect_sig_names(decl.dst, defined)
        collect_sig_names(decl.src, used)
    elif isinstance(decl, AHDL_COMB):
        for stm in decl.stms:
            d, u = collect_def_use(stm)
            defined |= d
            used |= u
    elif isinstance(decl, AHDL_IF):
        for cond in decl.conds:
            if cond is not None:
                collect_sig_names(cond, used)
        for block in decl.blocks:
            d, u = collect_def_use(block)
            defined |= d
            used |= u
    elif isinstance(decl, AHDL_BLOCK):
        for stm in decl.codes:
            d, u = collect_def_use(stm)
            defined |= d
            used |= u
    elif isinstance(decl, AHDL_CASE):
        collect_sig_names(decl.sel, used)
        for item in decl.items:
            d, u = collect_def_use(item)
            defined |= d
            used |= u
    elif isinstance(decl, AHDL_CASE_ITEM):
        d, u = collect_def_use(decl.block)
        defined |= d
        used |= u
    return defined, used


def toposort_decls(decls: list) -> list:
    """Topologically sort AHDL declarations by signal dependencies.

    For each AHDL_ASSIGN, the dst signal is the 'definition' and signals
    appearing in src are 'uses'. A decl B depends on decl A if B uses a
    signal that A defines.  Returns a list in dependency order so that
    producers come before consumers. Cycles are broken by preserving the
    original relative order of the cycle members.
    """
    if len(decls) <= 1:
        return list(decls)

    # 1. Collect def/use info per decl
    defs: list[set[str]] = []
    uses: list[set[str]] = []
    for decl in decls:
        d, u = collect_def_use(decl)
        defs.append(d)
        uses.append(u)

    # 2. Build sig->decl_index map (which decl defines which signal)
    sig_to_def: dict[str, int] = {}
    for i, d in enumerate(defs):
        for sig_name in d:
            sig_to_def[sig_name] = i

    # 3. Build adjacency and in-degree for Kahn's algorithm
    n = len(decls)
    adj: dict[int, set[int]] = defaultdict(set)
    in_degree = [0] * n
    for i, u in enumerate(uses):
        for sig_name in u:
            j = sig_to_def.get(sig_name)
            if j is not None and j != i:
                if i not in adj[j]:
                    adj[j].add(i)
                    in_degree[i] += 1

    # 4. Kahn's algorithm
    queue = deque(i for i in range(n) if in_degree[i] == 0)
    result = []
    while queue:
        node = queue.popleft()
        result.append(node)
        for succ in sorted(adj[node]):  # sorted for determinism
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                queue.append(succ)

    # 5. If there are cycles, append remaining nodes in original order
    if len(result) < n:
        remaining = sorted(set(range(n)) - set(result))
        result.extend(remaining)

    return [decls[i] for i in result]
