from .common import error_info
from .scope import Scope
from .ir import CONST, TEMP, MOVE
from .irvisitor import IRTransformer
from .type import Type
from .typecheck import TypePropagation


class PortTypeProp(TypePropagation):
    def visit_NEW(self, ir):
        if ir.func_scope.is_port():
            assert self.scope.is_ctor() and self.scope.parent.is_module()
            attrs = {}
            ctor = ir.func_scope.find_ctor()
            for (_, a), p in zip(ir.args, ctor.params[1:]):
                if not a.is_a(CONST):
                    print(error_info(self.scope, ir.lineno))
                    raise RuntimeError('The port class constructor accepts only constants.')
                attrs[p.copy.name] = a.value

            attrs['direction'] = '?'
            attrs['root_symbol'] = self.current_stm.dst.symbol()
            if self.current_stm.is_a(MOVE) and self.current_stm.dst.is_a(TEMP):
                attrs['port_kind'] = 'internal'
            else:
                attrs['port_kind'] = 'external'
            if 'protocol' not in attrs:
                attrs['protocol'] = 'none'
            if 'init' not in attrs:
                attrs['init'] = 0
            port_typ = Type.port(ir.func_scope, attrs)
            #port_typ.freeze()
            ir.func_scope.return_type = port_typ
        return ir.func_scope.return_type

    def _set_type(self, sym, typ):
        if sym.typ.is_object() and sym.typ.get_scope().is_port() and typ.is_port():
            sym.set_type(typ)


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
            ctor = m.find_ctor()
            assert ctor
            typeprop.process(ctor)
            for w, args in m.workers:
                typeprop.process(w)

            #self.removes = []
            self.process(ctor)
            for w, args in m.workers:
                self.process(w)

            for field in m.class_fields().values():
                if field.typ.is_port() and field.typ.get_direction() == '?':
                    raise RuntimeError("The port '{}' is not used at all".format(field))

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
            if not sym.typ.has_direction():
                sym.typ.set_direction('?')
            di = sym.typ.get_direction()
            kind = sym.typ.get_port_kind()
            if kind == 'external':
                if di == '?':
                    sym.typ.set_direction(direction)
                    sym.typ.freeze()
                elif di != direction:
                    print(error_info(self.scope, ir.lineno))
                    raise RuntimeError('Port direction is conflicted')
            elif kind == 'internal':
                if direction == 'output':
                    if sym.typ.has_writer():
                        writer = sym.typ.get_writer()
                        if writer is not self.scope:
                            print(error_info(self.scope, ir.lineno))
                            raise RuntimeError('Writing to the port is conflicted')
                    else:
                        assert self.scope.is_worker() or self.scope.parent.is_module()
                        sym.typ.set_writer(self.scope)
        return ir

    def visit_SYSCALL(self, ir):
        if ir.name.startswith('polyphony.timing.wait_'):
            if (ir.name == 'polyphony.timing.wait_rising' or
                    ir.name == 'polyphony.timing.wait_falling'):
                ports = ir.args
            elif ir.name == 'polyphony.timing.wait_edge':
                ports = ir.args[2:]
            elif ir.name == 'polyphony.timing.wait_value':
                ports = ir.args[1:]
            for _, p in ports:
                port = p.symbol().typ
                assert port.is_port()
                di = port.get_direction()
                kind = port.get_port_kind()
                if kind == 'external':
                    if di == 'output':
                        print(error_info(self.scope, ir.lineno))
                        raise RuntimeError('Cannot wait for output port')
                    elif di == '?':
                        port.set_direction('input')
                        port.freeze()
        return ir

#    def visit_MOVE(self, ir):
#        ir.src = self.visit(ir.src)
#        ir.dst = self.visit(ir.dst)
#        #if ir.src.is_a(TEMP) and ir.src.symbol().is_param() and ir.src.symbol().typ.is_port():
#        #    return
#        self.new_stms.append(ir)
