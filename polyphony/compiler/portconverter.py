from collections import defaultdict
from .common import error_info
from .common import fail, warn
from .env import env
from .errors import Errors, Warnings
from .scope import Scope
from .ir import CONST, TEMP, MOVE
from .irvisitor import IRVisitor, IRTransformer
from .type import Type
from .typecheck import TypePropagation


class PortTypeProp(TypePropagation):
    def visit_NEW(self, ir):
        if ir.func_scope().is_port():
            assert self.scope.is_ctor() and self.scope.parent.is_module()
            attrs = {}
            ctor = ir.func_scope().find_ctor()
            for (_, a), p in zip(ir.args, ctor.params[1:]):
                if a.is_a(CONST):
                    if p.copy.name == 'direction':
                        di = self._normalize_direction(a.value)
                        if not di:
                            fail(self.current_stm,
                                 Errors.UNKNOWN_X_IS_SPECIFIED,
                                 ['direction', a.value])
                        attrs[p.copy.name] = di
                    else:
                        attrs[p.copy.name] = a.value
                elif a.is_a(TEMP) and a.symbol().typ.is_class():
                    attrs[p.copy.name] = a.symbol().typ.name
                else:
                    fail(self.current_stm, Errors.PORT_PARAM_MUST_BE_CONST)
            assert len(ir.func_scope().type_args) == 1
            assert 'direction' in attrs
            attrs['dtype'] = ir.func_scope().type_args[0]
            attrs['root_symbol'] = self.current_stm.dst.symbol()
            if self.current_stm.is_a(MOVE) and self.current_stm.dst.is_a(TEMP):
                attrs['port_kind'] = 'internal'
            else:
                if attrs['direction'] == 'input' or attrs['direction'] == 'output':
                    attrs['port_kind'] = 'external'
                else:
                    attrs['port_kind'] = 'internal'
            if 'protocol' not in attrs:
                attrs['protocol'] = 'none'
            if 'init' not in attrs or attrs['init'] is None:
                attrs['init'] = 0
            port_typ = Type.port(ir.func_scope(), attrs)
            #port_typ.freeze()
            ir.func_scope().return_type = port_typ
        return ir.func_scope().return_type

    def _normalize_direction(self, di):
        if di == 'in' or di == 'input' or di == 'i':
            return 'input'
        elif di == 'out' or di == 'output' or di == 'o':
            return 'output'
        elif di == 'any' or not di:
            return 'any'
        return ''

    def visit_CALL(self, ir):
        if ir.func_scope().is_method() and ir.func_scope().parent.is_port():
            sym = ir.func.tail()
            assert sym.typ.is_port()
            kind = sym.typ.get_port_kind()
            root = sym.typ.get_root_symbol()
            port_owner = root.scope
            # if port is a local variable, we modify the port owner its parent
            if port_owner.is_method():
                port_owner = port_owner.parent
            if self.scope.is_worker():
                scope = self.scope.worker_owner
            elif self.scope.is_method():
                scope = self.scope.parent
            else:
                scope = self.scope
            if not scope.is_subclassof(port_owner) and kind == 'internal':
                fail(self.current_stm, Errors.PORT_ACCESS_IS_NOT_ALLOWED)
        return super().visit_CALL(ir)


class PortConverter(IRTransformer):
    def __init__(self):
        super().__init__()
        self.writers = defaultdict(set)
        self.readers = defaultdict(set)

    def process_all(self):
        scopes = Scope.get_scopes(with_class=True)
        modules = [s for s in scopes if s.is_module()]
        if not modules:
            return
        typeprop = PortTypeProp()
        for m in modules:
            if not m.is_instantiated():
                continue
            ctor = m.find_ctor()
            assert ctor
            typeprop.process(ctor)
            for w, args in m.workers:
                typeprop.process(w)
            for caller in env.depend_graph.preds(m):
                if caller.is_namespace():
                    continue
                typeprop.process(caller)

            self.union_ports = defaultdict(set)
            self.process(ctor)
            for w, args in m.workers:
                self.process(w)
            for caller in env.depend_graph.preds(m):
                if caller.is_namespace():
                    continue
                self.process(caller)

            # check for instance variable port
            for field in m.class_fields().values():
                if field.typ.is_port() and field not in self.readers and field not in self.writers:
                    if not env.depend_graph.preds(m):
                        continue
                    assert ctor.usedef
                    stm = ctor.usedef.get_stms_defining(field).pop()
                    warn(stm, Warnings.PORT_IS_NOT_USED,
                         [field.orig_name()])
            # check for local variable port
            for sym in ctor.symbols.values():
                if sym.typ.is_port() and sym not in self.readers and sym not in self.writers:
                    assert ctor.usedef
                    stms = ctor.usedef.get_stms_defining(sym)
                    # This symbol might not be used (e.g. ancestor symbol),
                    # so we have to check if its definition statement exists.
                    if stms:
                        warn(list(stms)[0], Warnings.PORT_IS_NOT_USED,
                             [sym.orig_name()])

    def _set_and_check_port_direction(self, expected_di, sym):
        port_typ = sym.typ
        rootsym = port_typ.get_root_symbol()
        di = port_typ.get_direction()
        kind = port_typ.get_port_kind()
        if kind == 'external':
            if di == 'any':
                port_typ.set_port_kind('internal')
                port_typ.set_direction('inout')
            elif di != expected_di:
                if sym.ancestor and sym.ancestor.scope is not sym.scope:
                    # the port has been accessed as opposite direction
                    # by a module includes original owner module
                    port_typ.set_port_kind('internal')
                    port_typ.set_direction('inout')
                else:
                    fail(self.current_stm, Errors.DIRECTION_IS_CONFLICTED,
                         [sym.orig_name()])
        elif kind == 'internal':
            if self.scope.is_worker():
                port_typ.set_direction('inout')
            else:
                fail(self.current_stm, Errors.DIRECTION_IS_CONFLICTED,
                     [sym.orig_name()])

        if expected_di == 'output':
            # write-write conflict
            if self.writers[rootsym]:
                assert len(self.writers[rootsym]) == 1
                writer = list(self.writers[rootsym])[0]
                if writer is not self.scope and writer.worker_owner is self.scope.worker_owner:
                    fail(self.current_stm, Errors.WRITING_IS_CONFLICTED,
                         [sym.orig_name()])
            else:
                if kind == 'internal':
                    assert self.scope.is_worker() or self.scope.parent.is_module()
                self.writers[rootsym].add(self.scope)
        elif expected_di == 'input':
            # read-read conflict
            if self.readers[rootsym]:
                if all([s.is_testbench() for s in self.readers[rootsym]]):
                    if self.scope.is_testbench():
                        self.readers[rootsym].add(self.scope)
                elif port_typ.get_scope().name.startswith('polyphony.io.Port') and port_typ.get_protocol() == 'none':
                    pass
                else:
                    assert len(self.readers[rootsym]) == 1
                    reader = list(self.readers[rootsym])[0]
                    if reader is not self.scope and reader.worker_owner is self.scope.worker_owner:
                        fail(self.current_stm, Errors.READING_IS_CONFLICTED,
                             [sym.orig_name()])
            else:
                if kind == 'internal':
                    assert self.scope.is_worker() or self.scope.parent.is_module()
                self.readers[rootsym].add(self.scope)

    def _get_port_owner(self, sym):
        assert sym.typ.is_port()
        root = sym.typ.get_root_symbol()
        if root.scope.is_ctor():
            return root.scope.parent
        else:
            return root.scope

    def _check_port_direction(self, sym, func_scope):
        if func_scope.name.startswith('polyphony.io.Queue'):
            if func_scope.orig_name in ('wr', 'full'):
                expected_di = 'output'
            else:
                expected_di = 'input'
        else:
            if func_scope.orig_name == 'wr':
                expected_di = 'output'
            else:
                expected_di = 'input'
        port_owner = self._get_port_owner(sym)
        if ((self.scope.is_worker() and not self.scope.worker_owner.is_subclassof(port_owner)) or
                not self.scope.is_worker()):
            expected_di = 'output' if expected_di == 'input' else 'input'
        if sym in self.union_ports:
            for s in self.union_ports[sym]:
                self._set_and_check_port_direction(expected_di, s)
        else:
            self._set_and_check_port_direction(expected_di, sym)

    def visit_CALL(self, ir):
        if not ir.func_scope().is_lib():
            return ir
        if ir.func_scope().is_method() and ir.func_scope().parent.is_port():
            sym = ir.func.tail()
            assert sym.typ.is_port()
            self._check_port_direction(sym, ir.func_scope())
            if (self.current_stm.block.synth_params['scheduling'] == 'pipeline' and
                    self.scope.find_region(self.current_stm.block) is not self.scope.top_region()):
                root_sym = sym.typ.get_root_symbol()
                root_sym.add_tag('pipelined')
        return ir

    def visit_SYSCALL(self, ir):
        if ir.sym.name.startswith('polyphony.timing.wait_'):
            if (ir.sym.name == 'polyphony.timing.wait_rising' or
                    ir.sym.name == 'polyphony.timing.wait_falling'):
                ports = ir.args
            elif ir.sym.name == 'polyphony.timing.wait_edge':
                ports = ir.args[2:]
            elif ir.sym.name == 'polyphony.timing.wait_value':
                ports = ir.args[1:]
            for _, p in ports:
                port = p.symbol().typ
                assert port.is_port()
                di = port.get_direction()
                kind = port.get_port_kind()
                if kind == 'external':
                    port_owner = self._get_port_owner(p.symbol())
                    #port.set_direction('input')
                    #port.freeze()
                    if ((self.scope.is_worker() and not self.scope.worker_owner.is_subclassof(port_owner)) or
                            not self.scope.is_worker()):
                        if di == 'input':
                            fail(self.current_stm, Errors.CANNOT_WAIT_INPUT)
                    else:
                        if di == 'output':
                            fail(self.current_stm, Errors.CANNOT_WAIT_OUTPUT)
        return ir

    def visit_PHI(self, ir):
        if ir.var.symbol().typ.is_port():
            for arg in ir.args:
                self.union_ports[ir.var.symbol()].add(arg.symbol())
        super().visit_PHI(ir)


class FlattenPortList(IRTransformer):
    def visit_MREF(self, ir):
        memsym = ir.mem.symbol()
        memtyp = memsym.typ
        assert memtyp.is_seq()
        elm_t = memtyp.get_element()
        if not elm_t.is_object():
            return ir
        if not elm_t.get_scope().is_port():
            return ir
        if not ir.offset.is_a(CONST):
            return ir
        portname = '{}_{}'.format(memsym.name, ir.offset.value)
        scope = ir.mem.symbol().scope
        portsym = scope.find_sym(portname)
        assert portsym
        ir.mem.set_symbol(portsym)
        return ir.mem
