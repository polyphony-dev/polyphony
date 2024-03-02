from .symbol import Symbol
from .types.type import Type


builtin_mappings = {
    '__builtin__._assert': 'assert',
    '__builtin__._new': '$new',
}

builtin_symbols = {}

builtin_types = {
    'none', 'int', 'bool', 'str',
    'list', 'tuple', 'object',
    'type',
    'fuction',
}

def append_builtin(namespace, scope):
    if namespace.name == '__builtin__':
        if scope.name in builtin_mappings:
            asname = builtin_mappings[scope.name]
        else:
            asname = scope.base_name
    else:
        asname = scope.name

    sym = namespace.symbols[scope.base_name]
    assert isinstance(sym, Symbol)
    builtin_symbols[asname] = sym

def clear_builtins():
    builtin_symbols.clear()
