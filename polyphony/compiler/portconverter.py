from .common import error_info
from .scope import Scope
from .symbol import Symbol
from .ir import *
from .irvisitor import IRTransformer
from .type import Type
from .typecheck import TypePropagation

class PortTypeProp(TypePropagation):
    def visit_NEW(self, ir):
        if not ir.func_scope.is_module() and not ir.func_scope.is_lib():
            return ir.func_scope.return_type
        if ir.func_scope.is_port():
            attrs = {}
            ctor = ir.func_scope.find_ctor()
            for a, p in zip(ir.args, ctor.params[1:]):
                if not a.is_a(CONST):
                    print(error_info(self.scope, ir.lineno))
                    raise RuntimeError('The port class constructor accepts only constants.')
                attrs[p.copy.name] = a.value

            attrs['direction'] = '?'
            port_typ = Type.port(ir.func_scope, attrs)
            #port_typ.freeze()
            ir.func_scope.return_type = port_typ
        return ir.func_scope.return_type


class PortConverter(IRTransformer):
    def __init__(self):
        super().__init__()

    def process_all(self):
        scopes = Scope.get_class_scopes()
        top = None
        for s in scopes:
            if s.is_module():
                top = s
                break
        if not top:
            return
        typeprop = PortTypeProp()
        for caller in top.caller_scopes:
            typeprop.process(caller)
        
        ctor = top.find_ctor()
        typeprop.process(ctor)
        self.process(ctor)

        for method in top.children:
            if method.is_ctor():
                continue
            typeprop.process(method)
        for method in top.children:
            if method.is_ctor():
                continue
            self.process(method)

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
            dir = sym.typ.get_direction()
            if dir == '?':
                sym.typ.set_direction(direction)
                sym.typ.freeze()
            elif dir != direction:
                raise RuntimeError('Port direction is conflicted')
        return ir
