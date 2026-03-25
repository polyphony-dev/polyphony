import re
from collections import defaultdict, deque

from polyphony.compiler.ahdl.ahdl import AHDL, AHDL_ASSIGN, AHDL_OP, AHDL_VAR, Ctx
from polyphony.compiler.ahdl.ahdlvisitor import AHDLVisitor


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
    defs: list[set[str]] = []   # defs[i] = signal names defined by decls[i]
    uses: list[set[str]] = []   # uses[i] = signal names used by decls[i]
    for decl in decls:
        d, u = _collect_def_use(decl)
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


def _collect_def_use(decl) -> tuple[set[str], set[str]]:
    """Return (defined_signals, used_signals) for a single decl."""
    from polyphony.compiler.ahdl.ahdl import (
        AHDL_BLOCK, AHDL_CASE, AHDL_CASE_ITEM, AHDL_COMB, AHDL_IF, AHDL_MOVE,
    )
    defined: set[str] = set()
    used: set[str] = set()
    if isinstance(decl, (AHDL_ASSIGN, AHDL_MOVE)):
        _collect_sig_names(decl.dst, defined)
        _collect_sig_names(decl.src, used)
    elif isinstance(decl, AHDL_COMB):
        for stm in decl.stms:
            d, u = _collect_def_use(stm)
            defined |= d
            used |= u
    elif isinstance(decl, AHDL_IF):
        for cond in decl.conds:
            if cond is not None:
                _collect_sig_names(cond, used)
        for block in decl.blocks:
            d, u = _collect_def_use(block)
            defined |= d
            used |= u
    elif isinstance(decl, AHDL_BLOCK):
        for stm in decl.codes:
            d, u = _collect_def_use(stm)
            defined |= d
            used |= u
    elif isinstance(decl, AHDL_CASE):
        _collect_sig_names(decl.sel, used)
        for item in decl.items:
            d, u = _collect_def_use(item)
            defined |= d
            used |= u
    elif isinstance(decl, AHDL_CASE_ITEM):
        d, u = _collect_def_use(decl.block)
        defined |= d
        used |= u
    return defined, used


def _collect_sig_names(node, names: set[str]):
    """Recursively collect signal names from an AHDL expression tree."""
    from polyphony.compiler.ahdl.ahdl import (
        AHDL_CONST, AHDL_FUNCALL, AHDL_IF_EXP, AHDL_MEMVAR,
        AHDL_SUBSCRIPT, AHDL_SYMBOL,
    )
    if isinstance(node, AHDL_VAR):
        names.add(node.vars[-1].name)
    elif isinstance(node, AHDL_SUBSCRIPT):
        names.add(node.memvar.vars[-1].name)
        _collect_sig_names(node.offset, names)
    elif isinstance(node, AHDL_MEMVAR):
        names.add(node.vars[-1].name)
    elif isinstance(node, AHDL_OP):
        for arg in node.args:
            _collect_sig_names(arg, names)
    elif isinstance(node, AHDL_IF_EXP):
        _collect_sig_names(node.cond, names)
        _collect_sig_names(node.lexp, names)
        _collect_sig_names(node.rexp, names)
    elif isinstance(node, AHDL_FUNCALL):
        for arg in node.args:
            _collect_sig_names(arg, names)
    elif isinstance(node, (AHDL_CONST, AHDL_SYMBOL)):
        pass

_CSAFE_RE = re.compile(r'[^A-Za-z0-9_]')


def _c_safe_name(name: str) -> str:
    """Sanitize a signal name for use as a C identifier."""
    return _CSAFE_RE.sub('_', name)


class AHDLToCTranspiler(AHDLVisitor):
    """Transpiles AHDL to C code with zero-copy shared buffer."""

    _BINOP_MAP = {
        'Add': '+', 'Sub': '-', 'Mult': '*',
        'Mod': '%', 'LShift': '<<', 'RShift': '>>',
        'BitOr': '|', 'BitXor': '^', 'BitAnd': '&',
    }
    _FLOORDIV = 'FloorDiv'
    _RELOP_MAP = {
        'And': '&&', 'Or': '||',
        'Eq': '==', 'NotEq': '!=',
        'Lt': '<', 'LtE': '<=', 'Gt': '>', 'GtE': '>=',
        'Is': '==', 'IsNot': '!=',
    }
    _UNOP_MAP = {
        'USub': '-', 'UAdd': '+', 'Not': '!',
    }

    def __init__(self):
        super().__init__()
        self._sig_map: dict[str, int] = {}
        self._port_map: dict[str, int] = {}
        self._sig_count: int = 0
        self._const_map: dict[str, int] = {}
        self._sig_widths: list[tuple[int, bool]] = []
        self._lines: list[str] = []
        self._func_param_map: dict[str, str] = {}
        self._name_to_cname: dict[str, str] = {}  # raw signal name -> C-safe name

    def assign_signal_ids(self, hdlscope):
        self._sig_map = {}
        self._port_map = {}
        self._const_map = {}
        self._sig_widths = []
        self._reg_cur_slots = 0  # number of cur slots (for memcpy in update_regs)

        # Phase 0: collect constants
        self._collect_constants(hdlscope, '')

        # Phase 1: collect all signals into reg_list and net_list
        reg_list: list[tuple[str, object]] = []  # (cname, sig)
        net_list: list[tuple[str, object]] = []
        port_names: list[tuple[str, str]] = []   # (raw_name, cname)
        self._collect_signals(hdlscope, '', reg_list, net_list, port_names)

        # Phase 2: assign cur slots for regs (contiguous)
        idx = 0
        for cname, sig in reg_list:
            slots = self._reg_cur_slot_count(sig)
            self._sig_map[cname] = idx
            is_signed = sig.is_int()
            w = sig.width[0] if sig.is_regarray() else sig.width
            for _ in range(slots):
                self._sig_widths.append((w, is_signed))
            idx += slots
        reg_cur_total = idx

        # Phase 3: assign next slots for regs (contiguous, right after cur)
        for cname, sig in reg_list:
            slots = self._reg_cur_slot_count(sig)
            self._sig_map[cname + '_next'] = idx
            is_signed = sig.is_int()
            w = sig.width[0] if sig.is_regarray() else sig.width
            for _ in range(slots):
                self._sig_widths.append((w, is_signed))
            idx += slots

        # Phase 4: assign slots for nets
        for cname, sig in net_list:
            self._sig_map[cname] = idx
            is_signed = sig.is_int()
            if sig.is_netarray():
                _, length = sig.width
                for _ in range(length):
                    self._sig_widths.append((sig.width[0], is_signed))
                idx += length
            else:
                self._sig_widths.append((sig.width, is_signed))
                idx += 1

        # Set port_map
        for raw_name, cname in port_names:
            self._port_map[raw_name] = self._sig_map[cname]

        self._sig_count = idx
        self._reg_cur_slots = reg_cur_total
        return dict(self._sig_map), dict(self._port_map), self._sig_count

    def _collect_constants(self, scope, prefix):
        for sig in scope.get_signals(include_tags={'constant'}):
            if sig in scope.constants:
                key = f'{prefix}{sig.name}' if prefix else sig.name
                self._const_map[key] = scope.constants[sig]
        for sub_sig, sub_scope in scope.subscopes.items():
            sub_prefix = f'{prefix}{_c_safe_name(sub_sig.name)}_'
            self._collect_constants(sub_scope, sub_prefix)

    def _collect_signals(self, scope, prefix, reg_list, net_list, port_names):
        """Collect all signals from scope (and subscopes) into reg/net lists."""
        signals = scope.get_signals(
            include_tags={'reg', 'net', 'regarray', 'netarray'},
            exclude_tags={'input', 'output'},
        )
        rom_signals = scope.get_signals(include_tags={'rom'})
        all_signals = list(signals) + [
            s for s in rom_signals if s.name not in {sig.name for sig in signals}
        ]
        for sig in all_signals:
            if sig.is_constant():
                if sig in scope.constants:
                    key = f'{prefix}{sig.name}' if prefix else sig.name
                    self._const_map[key] = scope.constants[sig]
                continue
            cname = f'{prefix}{_c_safe_name(sig.name)}' if prefix else _c_safe_name(sig.name)
            raw = f'{prefix}{sig.name}' if prefix else sig.name
            self._name_to_cname[raw] = cname
            if sig.is_reg() or sig.is_regarray():
                reg_list.append((cname, sig))
            else:
                net_list.append((cname, sig))

        # Ports
        port_signals = scope.get_signals(include_tags={'input', 'output'})
        for sig in port_signals:
            if sig.is_constant() or sig.is_rom():
                continue
            cname = f'{prefix}{_c_safe_name(sig.name)}' if prefix else _c_safe_name(sig.name)
            raw = f'{prefix}{sig.name}' if prefix else sig.name
            if cname not in self._name_to_cname.values():
                self._name_to_cname[raw] = cname
                if sig.is_reg() or sig.is_regarray():
                    reg_list.append((cname, sig))
                else:
                    net_list.append((cname, sig))
            port_names.append((sig.name, cname))

        # Recurse into subscopes
        for sub_sig, sub_scope in scope.subscopes.items():
            sub_prefix = f'{prefix}{_c_safe_name(sub_sig.name)}_'
            self._collect_signals(sub_scope, sub_prefix, reg_list, net_list, port_names)

    @staticmethod
    def _reg_cur_slot_count(sig) -> int:
        if sig.is_regarray():
            return sig.width[1]
        return 1

    def emit_signal_defines(self):
        lines = []
        defines = []
        for name, idx in sorted(self._sig_map.items(), key=lambda x: x[1]):
            defines.append((f'S_{name}', idx))
        for name, idx in self._sig_map.items():
            if name.endswith('_next'):
                base_name = name[:-5]
                if base_name in self._sig_map:
                    length = idx - self._sig_map[base_name]
                    if length > 1:
                        defines.append((f'S_{base_name}_LEN', length))
        defines.append(('S_NUM_SIGNALS', self._sig_count))
        max_name_len = max(len(d[0]) for d in defines) if defines else 0
        for macro, val in defines:
            lines.append(f'#define {macro:<{max_name_len}} {val}')
        return '\n'.join(lines)

    def visit_AHDL_CONST(self, ahdl):
        if isinstance(ahdl.value, str):
            return '0'
        return str(ahdl.value)

    def visit_AHDL_VAR(self, ahdl):
        sig = ahdl.vars[-1]
        raw_name = sig.name

        # Check func_param_map first (leaf name only)
        if raw_name in self._func_param_map:
            return self._func_param_map[raw_name]

        # Build hierarchical name for multi-level vars
        if len(ahdl.vars) > 1:
            hdl_name = '_'.join(s.name for s in ahdl.vars)
        else:
            hdl_name = raw_name

        # Check constant map with hierarchical name
        if hdl_name in self._const_map:
            return str(self._const_map[hdl_name])
        if raw_name in self._const_map:
            return str(self._const_map[raw_name])

        cname = self._name_to_cname.get(hdl_name, _c_safe_name(hdl_name))
        if ahdl.ctx == Ctx.STORE and sig.is_reg():
            return f's[S_{cname}_next]'
        return f's[S_{cname}]'

    def visit_AHDL_OP(self, ahdl):
        if ahdl.op == self._FLOORDIV:
            l = self.visit(ahdl.args[0])
            r = self.visit(ahdl.args[1])
            return f'floordiv({l}, {r})'
        elif ahdl.op in self._BINOP_MAP:
            l = self.visit(ahdl.args[0])
            r = self.visit(ahdl.args[1])
            return f'({l} {self._BINOP_MAP[ahdl.op]} {r})'
        elif ahdl.op in self._RELOP_MAP:
            l = self.visit(ahdl.args[0])
            r = self.visit(ahdl.args[1])
            return f'({l} {self._RELOP_MAP[ahdl.op]} {r})'
        elif ahdl.op == 'Invert':
            operand = ahdl.args[0]
            a = self.visit(operand)
            w = self._infer_width(operand)
            return f'mask(~({a}), {w})'
        elif ahdl.op in self._UNOP_MAP:
            a = self.visit(ahdl.args[0])
            return f'({self._UNOP_MAP[ahdl.op]}{a})'
        raise NotImplementedError(f'Unsupported op: {ahdl.op}')

    def _infer_width(self, ahdl_exp) -> int:
        """Infer the bit width of an AHDL expression."""
        if isinstance(ahdl_exp, AHDL_VAR):
            return ahdl_exp.sig.width
        if isinstance(ahdl_exp, AHDL_OP) and ahdl_exp.is_relop():
            return 1
        raise NotImplementedError(
            f'Cannot infer width for Invert operand: {type(ahdl_exp).__name__}'
        )

    def visit_AHDL_IF_EXP(self, ahdl):
        c = self.visit(ahdl.cond)
        l = self.visit(ahdl.lexp)
        r = self.visit(ahdl.rexp)
        return f'({c} ? {l} : {r})'

    def visit_AHDL_MEMVAR(self, ahdl):
        return self.visit_AHDL_VAR(ahdl)

    def visit_AHDL_SUBSCRIPT(self, ahdl):
        # Build hierarchical name from memvar.vars
        if len(ahdl.memvar.vars) > 1:
            hdl_name = '_'.join(s.name for s in ahdl.memvar.vars)
        else:
            hdl_name = ahdl.memvar.vars[-1].name
        cname = self._name_to_cname.get(hdl_name, _c_safe_name(hdl_name))
        offset = self.visit(ahdl.offset)
        sig = ahdl.memvar.vars[-1]
        if ahdl.ctx == Ctx.STORE and (sig.is_reg() or sig.is_regarray()):
            return f's[S_{cname}_next + {offset}]'
        return f's[S_{cname} + {offset}]'

    def visit_AHDL_FUNCALL(self, ahdl):
        func_name = _c_safe_name(ahdl.name.vars[-1].name)
        args = ', '.join(['s'] + [self.visit(a) for a in ahdl.args])
        return f'func_{func_name}({args})'

    def visit_AHDL_SYMBOL(self, ahdl):
        if ahdl.name == "'bz":
            return '0'
        raise NotImplementedError(f'Unsupported symbol: {ahdl.name}')

    # --- Statement visitors ---

    def _get_width(self, sig_name):
        idx = self._sig_map.get(sig_name)
        if idx is not None and idx < len(self._sig_widths):
            return self._sig_widths[idx][0]
        return 64

    def _is_signed(self, sig_name):
        idx = self._sig_map.get(sig_name)
        if idx is not None and idx < len(self._sig_widths):
            return self._sig_widths[idx][1]
        return False

    def _mask_expr(self, src_expr, sig_name):
        """Return mask (+ sext for signed) expression matching Python Integer semantics."""
        w = self._get_width(sig_name)
        if self._is_signed(sig_name):
            return f'sext(mask({src_expr}, {w}), {w})'
        return f'mask({src_expr}, {w})'

    def _sig_name_from_dst(self, dst):
        """Return the C-safe signal name from a dst node."""
        from polyphony.compiler.ahdl.ahdl import AHDL_SUBSCRIPT
        if isinstance(dst, AHDL_SUBSCRIPT):
            if len(dst.memvar.vars) > 1:
                raw = '_'.join(s.name for s in dst.memvar.vars)
            else:
                raw = dst.memvar.vars[-1].name
        else:
            if len(dst.vars) > 1:
                raw = '_'.join(s.name for s in dst.vars)
            else:
                raw = dst.vars[-1].name
        return self._name_to_cname.get(raw, _c_safe_name(raw))

    def visit_AHDL_MOVE(self, ahdl):
        dst_expr = self.visit(ahdl.dst)
        src_expr = self.visit(ahdl.src)
        sig_name = self._sig_name_from_dst(ahdl.dst)
        rhs = self._mask_expr(src_expr, sig_name)
        self._lines.append(f'    {dst_expr} = {rhs};')

    def visit_AHDL_ASSIGN(self, ahdl):
        dst_expr = self.visit(ahdl.dst)
        src_expr = self.visit(ahdl.src)
        sig_name = self._sig_name_from_dst(ahdl.dst)
        rhs = self._mask_expr(src_expr, sig_name)
        self._lines.append(f'    {{ int64_t prev = {dst_expr};')
        self._lines.append(f'      {dst_expr} = {rhs};')
        self._lines.append(f'      if ({dst_expr} != prev) updated = 1; }}')

    def visit_AHDL_CONNECT(self, ahdl):
        dst_expr = self.visit(ahdl.dst)
        src_expr = self.visit(ahdl.src)
        self._lines.append(f'    {dst_expr} = {src_expr};')

    # --- Control flow visitors ---

    def visit_AHDL_IF(self, ahdl):
        for i, (cond, block) in enumerate(zip(ahdl.conds, ahdl.blocks)):
            if cond is None:
                self._lines.append('    } else {')
            elif i == 0:
                c = self.visit(cond)
                self._lines.append(f'    if ({c}) {{')
            else:
                c = self.visit(cond)
                self._lines.append(f'    }} else if ({c}) {{')
            self.visit(block)
        self._lines.append('    }')

    def visit_AHDL_TRANSITION_IF(self, ahdl):
        self.visit_AHDL_IF(ahdl)

    def visit_AHDL_PIPELINE_GUARD(self, ahdl):
        self.visit_AHDL_IF(ahdl)

    def visit_AHDL_CASE(self, ahdl):
        sel = self.visit(ahdl.sel)
        self._lines.append(f'    switch ({sel}) {{')
        for item in ahdl.items:
            self.visit(item)
        self._lines.append('    }')

    def visit_AHDL_CASE_ITEM(self, ahdl):
        val = self.visit(ahdl.val)
        self._lines.append(f'    case {val}: {{')
        self.visit(ahdl.block)
        self._lines.append('        break; }')

    # --- Remaining visitors ---

    def visit_AHDL_EVENT_TASK(self, ahdl):
        conditions = []
        for sig, edge in ahdl.events:
            cname = self._name_to_cname.get(sig.name, _c_safe_name(sig.name))
            if edge == 'rising':
                conditions.append(f's[S_{cname}] == 1')
            else:
                conditions.append(f's[S_{cname}] == 0')
        cond_str = ' && '.join(conditions)
        self._lines.append(f'    if ({cond_str}) {{')
        self.visit(ahdl.stm)
        self._lines.append('    }')

    def visit_AHDL_FUNCTION(self, ahdl):
        for stm in ahdl.stms:
            self.visit(stm)

    def visit_AHDL_PROCCALL(self, ahdl):
        if ahdl.name == '!hdl_print':
            args = ', '.join(self.visit(a) for a in ahdl.args)
            fmt = ' '.join(['%lld'] * len(ahdl.args))
            self._lines.append(f'    printf("{fmt}\\n", {args});')
        elif ahdl.name == '!hdl_assert':
            cond = self.visit(ahdl.args[0]) if ahdl.args else '0'
            self._lines.append(f'    if (!({cond})) {{ fprintf(stderr, "Assertion failed\\n"); abort(); }}')
        else:
            raise NotImplementedError(f'Unsupported proccall: {ahdl.name}')

    def visit_AHDL_NOP(self, ahdl):
        self._lines.append(f'    // nop: {ahdl.info}')

    def visit_AHDL_INLINE(self, ahdl):
        self._lines.append(f'    // inline')

    def visit_AHDL_CALLEE_PROLOG(self, ahdl):
        self._lines.append(f'    // callee_prolog')

    def visit_AHDL_CALLEE_EPILOG(self, ahdl):
        self._lines.append(f'    // callee_epilog')

    def visit_AHDL_IO_READ(self, ahdl):
        pass

    def visit_AHDL_IO_WRITE(self, ahdl):
        pass

    def visit_AHDL_META_WAIT(self, ahdl):
        self._lines.append(f'    // meta_wait')

    def visit_AHDL_META_OP(self, ahdl):
        self._lines.append(f'    // meta_op')

    def visit_AHDL_MODULECALL(self, ahdl):
        raise NotImplementedError('AHDL_MODULECALL not supported in csim')

    def visit_AHDL_TRANSITION(self, ahdl):
        raise NotImplementedError('AHDL_TRANSITION not supported in csim')

    def generate(self, hdlscope):
        """Generate complete C source from an HDLScope.
        Returns (c_source, sig_map, port_map, sig_count).
        """
        sig_map, port_map, sig_count = self.assign_signal_ids(hdlscope)

        parts = []
        parts.append('#include "runtime_template.h"')
        parts.append('#include <string.h>\n')
        parts.append(self.emit_signal_defines())
        parts.append('')

        # ROM functions
        for func in getattr(hdlscope, 'functions', []):
            parts.append(self._emit_function_def(func))
            parts.append('')

        # module_eval_tasks
        parts.append('void module_eval_tasks(int64_t* s) {')
        self._lines = []
        for task in hdlscope.tasks:
            self.visit(task)
        parts.extend(self._lines)
        parts.append('}')
        parts.append('')

        # module_update_regs
        parts.append('void module_update_regs(int64_t* s) {')
        parts.extend(self._emit_update_regs(hdlscope))
        parts.append('}')
        parts.append('')

        # module_eval_decls
        from polyphony.simulator import MIN_EVAL_DECLS_ITERATIONS
        num_decls = len(hdlscope.decls)
        max_iter = max(num_decls + 1, MIN_EVAL_DECLS_ITERATIONS)
        parts.append('int module_eval_decls(int64_t* s) {')
        parts.append('    int updated = 1, iter = 0;')
        parts.append(f'    while (updated && iter < {max_iter}) {{')
        parts.append('        updated = 0;')
        self._lines = []
        for decl in toposort_decls(hdlscope.decls):
            self.visit(decl)
        parts.extend(self._lines)
        parts.append('        iter++;')
        parts.append('    }')
        parts.append('    return updated;')
        parts.append('}')

        c_source = '\n'.join(parts) + '\n'
        return c_source, sig_map, port_map, sig_count

    def _emit_update_regs(self, hdlscope):
        lines = []
        n = self._reg_cur_slots
        if n > 0:
            lines.append(f'    memcpy(s, s + {n}, {n} * sizeof(int64_t));')
        return lines

    def _emit_function_def(self, func):
        out_name = _c_safe_name(func.output.vars[-1].name)
        param_names = [f'p{i}' for i in range(len(func.inputs))]
        params = ', '.join([f'int64_t {p}' for p in param_names])
        func_name = _c_safe_name(func.name)
        lines = [f'static inline int64_t func_{func_name}(int64_t* s, {params}) {{']
        self._func_param_map = {}
        for inp, pname in zip(func.inputs, param_names):
            if hasattr(inp, 'vars') and inp.vars:
                self._func_param_map[inp.vars[-1].name] = pname
        self._lines = []
        for stm in func.stms:
            self.visit(stm)
        lines.extend(self._lines)
        lines.append(f'    return s[S_{out_name}];')
        lines.append('}')
        self._func_param_map = {}
        return '\n'.join(lines)
