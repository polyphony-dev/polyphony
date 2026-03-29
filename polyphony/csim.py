"""csim — C-transpiled simulation evaluator.

Provides CBufferSignal, CModelEvaluator, and CSimulatorModelBuilder
for zero-copy ctypes-based simulation acceleration.
"""
import ctypes
import os

from .simulator import Integer, Model, Net, Port, Reg, twos_comp


class CBufferSignal:
    """Reg/Net compatible signal backed by a ctypes int64_t buffer slot.

    Reads and writes go directly to the shared C buffer — no per-cycle
    sync required.  Instances replace model port attributes when using
    CModelEvaluator so that testbench port.wr()/rd() and _period()'s
    model.clk.val writes hit the C buffer automatically.

    When deferred=True, set() writes to a pending value instead of the
    buffer.  flush_pending() copies the pending value to the buffer.
    This matches Python Reg's double-buffering (set→next, update→val)
    for input ports where the HDL signal is a Net but the Python model
    uses a Reg.
    """

    __slots__ = ('_buf', '_idx', 'width', 'is_signed', 'signal', 'prev_val',
                 '_deferred', '_pending', '_has_pending')

    def __init__(self, buf, idx: int, width: int, is_signed: bool = False,
                 signal=None, deferred: bool = False):
        self._buf = buf
        self._idx = idx
        self.width = width
        self.is_signed = is_signed
        self.signal = signal
        self.prev_val = 0
        self._deferred = deferred
        self._pending = 0
        self._has_pending = False

    @property
    def val(self):
        return self._buf[self._idx]

    @val.setter
    def val(self, v):
        self.prev_val = self._buf[self._idx]
        self._buf[self._idx] = int(v) if isinstance(v, int) else 0

    @property
    def sign(self):
        return self.is_signed

    @property
    def next(self):
        return self._buf[self._idx]

    @next.setter
    def next(self, v):
        """Compatibility with Reg.next — C handles double-buffering,
        so just write to cur slot."""
        self._buf[self._idx] = int(v) if isinstance(v, int) else 0

    def set(self, v):
        if isinstance(v, int):
            mask = (1 << self.width) - 1
            val = v & mask
            if self.is_signed:
                val = twos_comp(val, self.width)
        else:
            val = 0
        if self._deferred:
            self._pending = val
            self._has_pending = True
        else:
            self.prev_val = self._buf[self._idx]
            self._buf[self._idx] = val

    def flush_pending(self):
        """Copy pending value to buffer. Called by CModelEvaluator.eval()."""
        if self._has_pending:
            self.prev_val = self._buf[self._idx]
            self._buf[self._idx] = self._pending
            self._has_pending = False

    def get(self):
        v = self._buf[self._idx]
        m = (1 << self.width) - 1
        v = v & m
        if self.is_signed:
            v = twos_comp(v, self.width)
        return v

    def toInteger(self):
        return Integer(self.get(), self.width, self.is_signed)

    def update(self):
        """No-op — C evaluator handles double-buffering."""
        pass


class CModelEvaluator:
    """Drop-in replacement for ModelEvaluator using compiled C via ctypes.
    Signal state lives in a flat int64_t[] buffer allocated on the Python side.
    C functions receive a pointer to this buffer -- zero-copy shared memory.
    """

    def __init__(self, so_path: str, sig_count: int, port_map: dict[str, int],
                 sig_map: dict[str, int] | None = None):
        self._buf = (ctypes.c_int64 * sig_count)()
        self._lib = ctypes.CDLL(so_path)
        self._port_map = port_map
        self._sig_map = sig_map or port_map
        self._sig_count = sig_count
        self._deferred_signals: list[CBufferSignal] = []
        self._all_port_signals: list[CBufferSignal] = []

        ptr_type = ctypes.POINTER(ctypes.c_int64)
        self._lib.module_eval_tasks.argtypes = [ptr_type]
        self._lib.module_eval_tasks.restype = None
        self._lib.module_update_regs.argtypes = [ptr_type]
        self._lib.module_update_regs.restype = None
        self._lib.module_eval_decls.argtypes = [ptr_type]
        self._lib.module_eval_decls.restype = ctypes.c_int

    def eval(self):
        self._lib.module_eval_tasks(self._buf)
        for sig in self._deferred_signals:
            sig.flush_pending()
        # Save prev_val before reg update for edge detection
        for sig in self._all_port_signals:
            sig.prev_val = self._buf[sig._idx]
        self._lib.module_update_regs(self._buf)
        rc = self._lib.module_eval_decls(self._buf)
        if rc != 0:
            import warnings
            warnings.warn('eval_decls: iteration limit reached')

    def read_port(self, name: str) -> int:
        return self._buf[self._port_map[name]]

    def write_port(self, name: str, value: int) -> None:
        self._buf[self._port_map[name]] = value

    def get_signal(self, name: str) -> int:
        """Read any signal (including internal) for watch/debug."""
        return self._buf[self._sig_map[name]]

    @staticmethod
    def bind_ports_to_buffer(model, buf, port_map, sig_map=None):
        """Replace model port attributes with CBufferSignal instances.

        After this call, model.clk.val = 1, port.wr(v), port.rd() all
        read/write the C buffer directly.

        Also walks sub-models (Handshake, Channel, etc.) and binds their
        Port attributes using sig_map with prefixed names (e.g. 'c_data').
        """
        deferred_list = []
        all_port_list = []
        for name, idx in port_map.items():
            attr = getattr(model, name, None)
            if attr is None:
                continue
            if isinstance(attr, Port):
                old = attr.value
                assert old is not None
                is_input = old.signal.is_input() if old.signal else False
                csig = CBufferSignal(buf, idx, old.width, old.sign,
                                     signal=old.signal, deferred=is_input)
                attr.value = csig  # type: ignore[assignment]  # CBufferSignal replaces Reg/Net
                all_port_list.append(csig)
                if is_input:
                    deferred_list.append(csig)
            elif isinstance(attr, (Reg, Net)):
                is_input = attr.signal.is_input() if attr.signal else False
                # clk/rst must not be deferred — they are set directly
                # by _period()/_reset() and must be visible in eval_tasks
                defer = is_input and name not in ('clk', 'rst')
                csig = CBufferSignal(buf, idx, attr.width, attr.sign,
                                     signal=attr.signal, deferred=defer)
                setattr(model, name, csig)
                all_port_list.append(csig)
                if defer:
                    deferred_list.append(csig)

        # Bind sub-model ports (Handshake, Channel, etc.) via sig_map
        if sig_map is None:
            return deferred_list, all_port_list
        for attr_name in list(vars(model).keys()):
            attr = getattr(model, attr_name)
            if not isinstance(attr, Model):
                continue
            sub_core = super(Model, attr).__getattribute__("__model")
            CModelEvaluator._bind_submodel(sub_core, buf, sig_map, attr_name,
                                           deferred_list, all_port_list)
        return deferred_list, all_port_list

    @staticmethod
    def _bind_submodel(sub_core, buf, sig_map, prefix, deferred_list, all_port_list):
        """Recursively bind sub-model Port/Reg/Net to C buffer via sig_map."""
        from polyphony.compiler.target.csim.csimgen import _c_safe_name
        for attr_name in list(vars(sub_core).keys()):
            if attr_name.startswith('_'):
                continue
            attr = getattr(sub_core, attr_name)
            sig_key = _c_safe_name(f'{prefix}_{attr_name}')
            if isinstance(attr, Port) and attr.value is not None:
                if sig_key in sig_map:
                    old = attr.value
                    assert old is not None
                    idx = sig_map[sig_key]
                    is_input = old.signal.is_input() if old.signal else False
                    csig = CBufferSignal(buf, idx, old.width, old.sign,
                                         signal=old.signal, deferred=is_input)
                    attr.value = csig  # type: ignore[assignment]
                    all_port_list.append(csig)
                    if is_input:
                        deferred_list.append(csig)
            elif isinstance(attr, (Reg, Net)):
                if sig_key in sig_map:
                    idx = sig_map[sig_key]
                    csig = CBufferSignal(buf, idx, attr.width, attr.sign,
                                         signal=attr.signal)
                    setattr(sub_core, attr_name, csig)
                    all_port_list.append(csig)
            elif isinstance(attr, Model):
                nested_core = super(Model, attr).__getattribute__("__model")
                CModelEvaluator._bind_submodel(nested_core, buf, sig_map, sig_key,
                                               deferred_list, all_port_list)


class CSimulatorModelBuilder:
    """Builds CModelEvaluator from HDLScope via AHDLToCTranspiler + C compiler.

    The C compiler is selected via the CC environment variable (default: 'cc').
    """

    def _load_initial_values(self, ev, hdlscope, transpiler):
        """Write Reg initial values into the shared buffer."""
        self._load_scope_init(ev, hdlscope, transpiler, '')
        for sub_sig, sub_scope in hdlscope.subscopes.items():
            from polyphony.compiler.target.csim.csimgen import _c_safe_name
            prefix = _c_safe_name(sub_sig.name) + '_'
            self._load_subscope_init(ev, sub_scope, transpiler, prefix)

    def _load_scope_init(self, ev, hdlscope, transpiler, prefix):
        from polyphony.compiler.target.csim.csimgen import _c_safe_name
        sig_map = transpiler._sig_map
        for sig in hdlscope.get_signals(include_tags={'reg', 'regarray'}):
            if not sig.is_initializable():
                continue
            val = int(sig.init_value)
            cname = _c_safe_name(prefix + sig.name) if prefix else _c_safe_name(sig.name)
            if sig.is_reg() and cname in sig_map:
                ev._buf[sig_map[cname]] = val
                # Also set _next slot so reset doesn't overwrite with 0
                next_key = cname + '_next'
                if next_key in sig_map:
                    ev._buf[sig_map[next_key]] = val
            elif sig.is_regarray() and cname in sig_map:
                base = sig_map[cname]
                length = sig.width[1]
                for i in range(length):
                    ev._buf[base + i] = val
                # Also set _next slots for regarray
                next_key = cname + '_next'
                if next_key in sig_map:
                    next_base = sig_map[next_key]
                    for i in range(length):
                        ev._buf[next_base + i] = val

    def _load_subscope_init(self, ev, sub_scope, transpiler, prefix):
        self._load_scope_init(ev, sub_scope, transpiler, prefix)
        for sub_sig, nested_scope in sub_scope.subscopes.items():
            from polyphony.compiler.target.csim.csimgen import _c_safe_name
            nested_prefix = prefix + _c_safe_name(sub_sig.name) + '_'
            self._load_subscope_init(ev, nested_scope, transpiler, nested_prefix)

    def build(self, hdlscope, output_dir=None):
        import hashlib
        import subprocess
        import shutil
        from polyphony.compiler.target.csim.csimgen import AHDLToCTranspiler

        if output_dir is None:
            output_dir = os.path.join('.tmp', 'csim')
        os.makedirs(output_dir, exist_ok=True)

        transpiler = AHDLToCTranspiler()
        c_source, sig_map, port_map, sig_count = transpiler.generate(hdlscope)

        # Read runtime header for hash
        h_path = os.path.join(
            os.path.dirname(__file__),
            'compiler', 'target', 'csim', 'runtime_template.h',
        )
        with open(h_path) as f:
            h_content = f.read()

        module_name = getattr(hdlscope, 'name', 'module')
        c_path = os.path.join(output_dir, f'csim_{module_name}.c')
        so_path = os.path.join(output_dir, f'csim_{module_name}.so')
        hash_path = os.path.join(output_dir, f'csim_{module_name}.hash')

        src_hash = hashlib.md5((c_source + h_content).encode()).hexdigest()

        # Check cache
        if os.path.isfile(hash_path) and os.path.isfile(so_path):
            with open(hash_path) as f:
                if f.read().strip() == src_hash:
                    ev = CModelEvaluator(so_path, sig_count, port_map, sig_map)
                    self._load_initial_values(ev, hdlscope, transpiler)
                    return ev

        # Write C source
        with open(c_path, 'w') as f:
            f.write(c_source)

        # Copy runtime header next to source for #include
        shutil.copy2(h_path, os.path.join(output_dir, 'runtime_template.h'))

        # Compile (CC env var overrides default compiler)
        cc = os.environ.get('CC', 'cc')
        result = subprocess.run(
            [cc, '-O2', '-shared', '-fPIC',
             '-I', output_dir,
             '-o', so_path, c_path],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f'{cc} compilation failed:\n{result.stderr}')

        # Write hash
        with open(hash_path, 'w') as f:
            f.write(src_hash)

        ev = CModelEvaluator(so_path, sig_count, port_map, sig_map)
        self._load_initial_values(ev, hdlscope, transpiler)
        return ev
