from .common import error_info
from .scope import Scope
from .ir import CONST
from .irvisitor import IRTransformer
from .type import Type
from .typecheck import TypePropagation


class PortTypeProp(TypePropagation):
    def visit_NEW(self, ir):
        if ir.func_scope.is_port():
            attrs = {}
            ctor = ir.func_scope.find_ctor()
            for a, p in zip(ir.args, ctor.params[1:]):
                if not a.is_a(CONST):
                    print(error_info(self.scope, ir.lineno))
                    raise RuntimeError('The port class constructor accepts only constants.')
                attrs[p.copy.name] = a.value

            attrs['direction'] = '?'
            attrs['iosymbol'] = self.current_stm.dst.symbol()
            port_typ = Type.port(ir.func_scope, attrs)
            #port_typ.freeze()
            ir.func_scope.return_type = port_typ
        return ir.func_scope.return_type


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

            self.process(ctor)

            for w, args in m.workers:
                self.process(w)

            for name, mv in m.class_fields.items():
                field = mv.dst.symbol()
                if field.typ.is_port() and field.typ.get_direction() == '?':
                    print(error_info(m, mv.lineno))
                    raise RuntimeError("The port '{}' is not used at all".format(mv.dst))

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
            if di == '?':
                sym.typ.set_direction(direction)
                sym.typ.freeze()
            elif di != direction:
                print(error_info(self.scope, ir.lineno))
                raise RuntimeError('Port direction is conflicted')
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
            for p in ports:
                port = p.symbol().typ
                assert port.is_port()
                di = port.get_direction()
                if di == 'output':
                    print(error_info(self.scope, ir.lineno))
                    raise RuntimeError('Cannot wait for output port')
                elif di == '?':
                    port.set_direction('input')
                    port.freeze()
        return ir
