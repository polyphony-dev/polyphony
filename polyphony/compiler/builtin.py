from .symbol import Symbol
from .type import Type


builtin_mappings = {
    '__builtin__.print': 'print',
    '__builtin__.range': 'range',
    '__builtin__.len': 'len',
    '__builtin__._assert': 'assert',
    '__builtin__.int': 'int',
    '__builtin__.bool': 'bool',
    'polyphony.verilog.write': 'polyphony.verilog.write',
    'polyphony.verilog.display': 'polyphony.verilog.display',
    'polyphony.timing.clksleep': 'polyphony.timing.clksleep',
    'polyphony.timing.wait_rising': 'polyphony.timing.wait_rising',
    'polyphony.timing.wait_falling': 'polyphony.timing.wait_falling',
    'polyphony.timing.wait_value': 'polyphony.timing.wait_value',
    'polyphony.timing.wait_edge': 'polyphony.timing.wait_edge',
    'polyphony.unroll': 'polyphony.unroll',
    'polyphony.pipelined': 'polyphony.pipelined',
}

builtin_symbols = {}


def append_builtin(builtin_scope, scope):
    assert scope.name in builtin_mappings
    name = builtin_mappings[scope.name]

    if scope.is_function():
        param_types = [sym.typ for sym, _, _ in scope.params]
        t = Type.function(scope, scope.return_type, param_types)
    elif scope.is_class():
        t = Type.klass(scope)
    else:
        assert False
    sym = Symbol(name, builtin_scope, {'builtin'}, t)
    builtin_symbols[name] = sym


lib_port_type_names = (
    'polyphony.io.Port',
    'polyphony.io.Queue',
)

lib_class_names = lib_port_type_names
