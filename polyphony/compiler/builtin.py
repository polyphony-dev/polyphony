from .type import Type

builtin_names = ['print', 'range', 'len', 'write', 'display']

builtin_return_type_table = {
    'print':Type.none_t,
    'range':Type.none_t,
    'len':Type.int_t,
    'write':Type.none_t,
    'display':Type.none_t,
    'assert':Type.none_t
}
