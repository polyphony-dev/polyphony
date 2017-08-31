from collections import defaultdict
from .common import error_info
from .common import fail
from .env import env
from .errors import Errors
from .scope import Scope
from .ir import CONST, TEMP, MOVE
from .irvisitor import IRVisitor, IRTransformer
from .type import Type
from .typecheck import TypePropagation


class PortTypeProp(TypePropagation):
    def visit_NEW(self, ir):
        if ir.func_scope.is_port():
            assert self.scope.is_ctor() and self.scope.parent.is_module()
            attrs = {}
            ctor = ir.func_scope.find_ctor()
            for (_, a), p in zip(ir.args, ctor.params[1:]):
                if a.is_a(CONST):
                    if p.copy.name == 'direction':
                        attrs[p.copy.name] = self._normalize_direction(a.value)
                    else:
                        attrs[p.copy.name] = a.value
                elif a.is_a(TEMP) and a.symbol().typ.is_class():
                    attrs[p.copy.name] = a.symbol().typ.name
                else:
                    fail(self.current_stm, Errors.PORT_PARAM_MUST_BE_CONST)
                    print(error_info(self.scope, ir.lineno))
                    raise RuntimeError('')

            assert len(ir.func_scope.type_args) == 1
            attrs['dtype'] = ir.func_scope.type_args[0]
            if 'direction' not in attrs or attrs['direction'] == 'auto':
                attrs['direction'] = '?'
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
            port_typ = Type.port(ir.func_scope, attrs)
            #port_typ.freeze()
            ir.func_scope.return_type = port_typ
        return ir.func_scope.return_type

    def _set_type(self, sym, typ):
        if sym.typ.is_object() and sym.typ.get_scope().is_port() and typ.is_port():
            sym.set_type(typ)

    def _normalize_direction(self, di):
        if di == 'in' or di == 'input' or di == 'i':
            return 'input'
        elif di == 'out' or di == 'output' or di == 'o':
            return 'output'
        elif di == 'any':
            return 'any'
        return '?'

    def visit_CALL(self, ir):
        if ir.func_scope.is_method() and ir.func_scope.parent.is_port():
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
            for caller in env.call_graph.preds(m):
                if caller.is_namespace():
                    continue
                typeprop.process(caller)

            self.union_ports = defaultdict(set)
            self.process(ctor)
            for w, args in m.workers:
                self.process(w)

            for field in m.class_fields().values():
                if field.typ.is_port() and field.typ.get_direction() == '?':
                    if not env.call_graph.preds(m):
                        continue
                    assert ctor.usedef
                    stm = ctor.usedef.get_stms_defining(field).pop()
                    fail(stm, Errors.PORT_IS_NOT_USED,
                         [field.orig_name()])
            for sym in ctor.symbols.values():
                if sym.typ.is_port() and sym.typ.get_direction() == '?':

                    assert ctor.usedef
                    stms = ctor.usedef.get_stms_defining(sym)
                    # This symbol might not be used (e.g. ancestor symbol),
                    # so we have to check if its definition statement exists.
                    if stms:
                        fail(stms.pop(), Errors.PORT_IS_NOT_USED,
                             [sym.orig_name()])

    def _set_and_check_port_direction(self, direction, sym, ir):
        port_typ = sym.typ
        if not port_typ.has_direction():
            port_typ.set_direction('?')
        di = port_typ.get_direction()
        kind = port_typ.get_port_kind()
        if kind == 'external':
            if di == '?':
                port_typ.set_direction(direction)
                port_typ.freeze()
            elif di == 'any':
                port_typ.set_port_kind('internal')
                port_typ.set_direction('inout')
            elif di != direction:
                if sym.ancestor and sym.ancestor.scope is not sym.scope:
                    # the port has been accessed as opposite direction
                    # by a module includes original owner module
                    port_typ.set_port_kind('internal')
                    port_typ.set_direction('inout')
                else:
                    fail(self.current_stm, Errors.DIRECTION_IS_CONFLICTED,
                         [sym.orig_name()])
        elif kind == 'internal':
            port_typ.set_direction('inout')

        if direction == 'output':
            # write-write conflict
            if port_typ.has_writer():
                writer = port_typ.get_writer()
                if writer is not self.scope and writer.worker_owner is self.scope.worker_owner:
                    fail(self.current_stm, Errors.WRITING_IS_CONFLICTED,
                         [sym.orig_name()])
            else:
                assert self.scope.is_worker() or self.scope.parent.is_module()
                port_typ.set_writer(self.scope)
        elif direction == 'input' and port_typ.get_scope().name.startswith('polyphony.io.Queue'):
            # read-read conflict
            if port_typ.has_reader():
                reader = port_typ.get_reader()
                if reader is not self.scope and reader.worker_owner is self.scope.worker_owner:
                    fail(self.current_stm, Errors.READING_IS_CONFLICTED,
                         [sym.orig_name()])
            else:
                assert self.scope.is_worker() or self.scope.parent.is_module()
                port_typ.set_reader(self.scope)

    def visit_CALL(self, ir):
        if not ir.func_scope.is_lib():
            return ir
        if ir.func_scope.is_method() and ir.func_scope.parent.is_port():
            sym = ir.func.tail()
            assert sym.typ.is_port()
            if ir.func_scope.orig_name == 'wr':
                direction = 'output'
            else:
                direction = 'input'
            if sym in self.union_ports:
                for s in self.union_ports[sym]:
                    self._set_and_check_port_direction(direction, s, ir)
            else:
                self._set_and_check_port_direction(direction, sym, ir)
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
                    if di == 'output':
                        fail(self.current_stm, Errors.CANNOT_WAIT_OUTPUT)
                    elif di == '?':
                        port.set_direction('input')
                        port.freeze()
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
