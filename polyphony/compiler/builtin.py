from .type import Type

builtin_names = ['print', 'range', 'len']

builtin_return_type_table = {
    'print':Type.none_t,
    'range':Type.none_t,
    'len':Type.int_t,
    'assert':Type.none_t
}