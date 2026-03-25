import re

from polyphony.compiler.ahdl.ahdl import AHDL, AHDL_OP, AHDL_VAR, Ctx
from polyphony.compiler.ahdl.ahdlvisitor import AHDLVisitor

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
        idx = 0

        # Collect constants (state labels, etc.) into _const_map
        for sig in hdlscope.get_signals(include_tags={'constant'}):
            if sig in hdlscope.constants:
                self._const_map[sig.name] = hdlscope.constants[sig]

        signals = hdlscope.get_signals(
            include_tags={'reg', 'net', 'regarray', 'netarray'},
            exclude_tags={'input', 'output'},
        )
        # Also include ROM signals (may only have 'rom' tag, not regarray/netarray)
        rom_signals = hdlscope.get_signals(include_tags={'rom'})
        all_signals = list(signals) + [s for s in rom_signals if s.name not in {sig.name for sig in signals}]
        for sig in all_signals:
            if sig.is_constant():
                if sig in hdlscope.constants:
                    self._const_map[sig.name] = hdlscope.constants[sig]
                continue
            idx = self._assign_one(sig, idx)

        port_signals = hdlscope.get_signals(include_tags={'input', 'output'})
        for sig in port_signals:
            if sig.is_constant() or sig.is_rom():
                continue
            cname = self._name_to_cname.get(sig.name)
            if cname is None:
                idx = self._assign_one(sig, idx)
                cname = self._name_to_cname[sig.name]
            self._port_map[sig.name] = self._sig_map[cname]

        # Recurse into subscopes
        for sub_sig, sub_scope in hdlscope.subscopes.items():
            idx = self._assign_subscope_ids(_c_safe_name(sub_sig.name), sub_scope, idx)

        self._sig_count = idx
        return dict(self._sig_map), dict(self._port_map), self._sig_count

    def _assign_one(self, sig, idx):
        is_signed = sig.is_int()
        cname = _c_safe_name(sig.name)
        self._name_to_cname[sig.name] = cname
        if sig.is_regarray():
            elem_w, length = sig.width
            self._sig_map[cname] = idx
            for _ in range(length):
                self._sig_widths.append((elem_w, is_signed))
            self._sig_map[cname + '_next'] = idx + length
            for _ in range(length):
                self._sig_widths.append((elem_w, is_signed))
            idx += 2 * length
        elif sig.is_netarray():
            _, length = sig.width
            self._sig_map[cname] = idx
            for _ in range(length):
                self._sig_widths.append((sig.width[0], is_signed))
            idx += length
        elif sig.is_reg():
            self._sig_map[cname] = idx
            self._sig_widths.append((sig.width, is_signed))
            self._sig_map[cname + '_next'] = idx + 1
            self._sig_widths.append((sig.width, is_signed))
            idx += 2
        else:
            self._sig_map[cname] = idx
            self._sig_widths.append((sig.width, is_signed))
            idx += 1
        return idx

    def _assign_subscope_ids(self, prefix, sub_scope, idx):
        """Recursively assign signal IDs for a subscope with a name prefix."""
        # Collect constants with prefixed names
        for sig in sub_scope.get_signals(include_tags={'constant'}):
            if sig in sub_scope.constants:
                self._const_map[f'{prefix}_{sig.name}'] = sub_scope.constants[sig]

        signals = sub_scope.get_signals(
            include_tags={'reg', 'net', 'regarray', 'netarray'},
            exclude_tags={'input', 'output'},
        )
        rom_signals = sub_scope.get_signals(include_tags={'rom'})
        all_signals = list(signals) + [s for s in rom_signals if s.name not in {sig.name for sig in signals}]
        for sig in all_signals:
            if sig.is_constant():
                if sig in sub_scope.constants:
                    self._const_map[f'{prefix}_{sig.name}'] = sub_scope.constants[sig]
                continue
            idx = self._assign_one_prefixed(prefix, sig, idx)

        port_signals = sub_scope.get_signals(include_tags={'input', 'output'})
        for sig in port_signals:
            if sig.is_constant() or sig.is_rom():
                continue
            prefixed = f'{prefix}_{_c_safe_name(sig.name)}'
            if prefixed not in self._sig_map:
                idx = self._assign_one_prefixed(prefix, sig, idx)

        # Recurse into nested subscopes
        for nested_sig, nested_scope in sub_scope.subscopes.items():
            nested_prefix = f'{prefix}_{_c_safe_name(nested_sig.name)}'
            idx = self._assign_subscope_ids(nested_prefix, nested_scope, idx)

        return idx

    def _assign_one_prefixed(self, prefix, sig, idx):
        """Assign buffer slots for a signal with a name prefix."""
        is_signed = sig.is_int()
        cname = f'{prefix}_{_c_safe_name(sig.name)}'
        # Map both the prefixed raw name and the c-safe name
        raw_prefixed = f'{prefix}_{sig.name}'
        self._name_to_cname[raw_prefixed] = cname
        if sig.is_regarray():
            elem_w, length = sig.width
            self._sig_map[cname] = idx
            for _ in range(length):
                self._sig_widths.append((elem_w, is_signed))
            self._sig_map[cname + '_next'] = idx + length
            for _ in range(length):
                self._sig_widths.append((elem_w, is_signed))
            idx += 2 * length
        elif sig.is_netarray():
            _, length = sig.width
            self._sig_map[cname] = idx
            for _ in range(length):
                self._sig_widths.append((sig.width[0], is_signed))
            idx += length
        elif sig.is_reg():
            self._sig_map[cname] = idx
            self._sig_widths.append((sig.width, is_signed))
            self._sig_map[cname + '_next'] = idx + 1
            self._sig_widths.append((sig.width, is_signed))
            idx += 2
        else:
            self._sig_map[cname] = idx
            self._sig_widths.append((sig.width, is_signed))
            idx += 1
        return idx

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
        w = self._get_width(sig_name)
        self._lines.append(f'    {dst_expr} = mask({src_expr}, {w});')

    def visit_AHDL_ASSIGN(self, ahdl):
        dst_expr = self.visit(ahdl.dst)
        src_expr = self.visit(ahdl.src)
        sig_name = self._sig_name_from_dst(ahdl.dst)
        w = self._get_width(sig_name)
        self._lines.append(f'    {{ int64_t prev = {dst_expr};')
        self._lines.append(f'      {dst_expr} = mask({src_expr}, {w});')
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
        parts.append('#include "runtime_template.h"\n')
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
        parts.append('int module_eval_decls(int64_t* s) {')
        parts.append('    int updated = 1, iter = 0;')
        parts.append('    while (updated && iter < 1000) {')
        parts.append('        updated = 0;')
        self._lines = []
        for decl in hdlscope.decls:
            self.visit(decl)
        parts.extend(self._lines)
        parts.append('        iter++;')
        parts.append('    }')
        parts.append('    return (iter >= 1000) ? 1 : 0;')
        parts.append('}')

        c_source = '\n'.join(parts) + '\n'
        return c_source, sig_map, port_map, sig_count

    def _emit_update_regs(self, hdlscope):
        lines = []
        seen = set()
        self._emit_update_regs_for_scope(hdlscope, '', lines, seen)
        return lines

    def _emit_update_regs_for_scope(self, hdlscope, prefix, lines, seen):
        signals = hdlscope.get_signals(
            include_tags={'reg', 'net', 'regarray', 'netarray'},
            exclude_tags={'input', 'output'},
        )
        port_signals = hdlscope.get_signals(include_tags={'input', 'output'})
        for sig in list(signals) + list(port_signals):
            raw = f'{prefix}{sig.name}' if prefix else sig.name
            if raw in seen:
                continue
            seen.add(raw)
            cname = self._name_to_cname.get(raw, _c_safe_name(raw))
            if sig.is_reg():
                lines.append(f'    s[S_{cname}] = s[S_{cname}_next];')
            elif sig.is_regarray():
                length = sig.width[1]
                lines.append(f'    for (int i = 0; i < {length}; i++)')
                lines.append(f'        s[S_{cname} + i] = s[S_{cname}_next + i];')
        # Recurse into subscopes
        for sub_sig, sub_scope in hdlscope.subscopes.items():
            sub_prefix = f'{prefix}{_c_safe_name(sub_sig.name)}_'
            self._emit_update_regs_for_scope(sub_scope, sub_prefix, lines, seen)

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
