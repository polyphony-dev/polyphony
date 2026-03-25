from polyphony.compiler.ahdl.ahdl import AHDL, Ctx
from polyphony.compiler.ahdl.ahdlvisitor import AHDLVisitor


class AHDLToCTranspiler(AHDLVisitor):
    """Transpiles AHDL to C code with zero-copy shared buffer."""

    def __init__(self):
        super().__init__()
        self._sig_map: dict[str, int] = {}
        self._port_map: dict[str, int] = {}
        self._sig_count: int = 0
        self._const_map: dict[str, int] = {}
        self._sig_widths: list[tuple[int, bool]] = []
        self._lines: list[str] = []

    def assign_signal_ids(self, hdlscope):
        self._sig_map = {}
        self._port_map = {}
        self._const_map = {}
        self._sig_widths = []
        idx = 0

        signals = hdlscope.get_signals(
            include_tags={'reg', 'net', 'regarray', 'netarray'},
            exclude_tags={'input', 'output'},
        )
        for sig in signals:
            if sig.is_constant() or sig.is_rom():
                if sig.is_constant() and sig in hdlscope.constants:
                    self._const_map[sig.name] = hdlscope.constants[sig]
                continue
            idx = self._assign_one(sig, idx)

        port_signals = hdlscope.get_signals(include_tags={'input', 'output'})
        for sig in port_signals:
            if sig.is_constant() or sig.is_rom():
                continue
            if sig.name not in self._sig_map:
                idx = self._assign_one(sig, idx)
            self._port_map[sig.name] = self._sig_map[sig.name]

        self._sig_count = idx
        return dict(self._sig_map), dict(self._port_map), self._sig_count

    def _assign_one(self, sig, idx):
        is_signed = sig.is_int()
        if sig.is_regarray():
            elem_w, length = sig.width
            self._sig_map[sig.name] = idx
            for _ in range(length):
                self._sig_widths.append((elem_w, is_signed))
            self._sig_map[sig.name + '_next'] = idx + length
            for _ in range(length):
                self._sig_widths.append((elem_w, is_signed))
            idx += 2 * length
        elif sig.is_netarray():
            _, length = sig.width
            self._sig_map[sig.name] = idx
            for _ in range(length):
                self._sig_widths.append((sig.width[0], is_signed))
            idx += length
        elif sig.is_reg():
            self._sig_map[sig.name] = idx
            self._sig_widths.append((sig.width, is_signed))
            self._sig_map[sig.name + '_next'] = idx + 1
            self._sig_widths.append((sig.width, is_signed))
            idx += 2
        else:
            self._sig_map[sig.name] = idx
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
