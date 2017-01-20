from .type import Type

builtin_return_type_table = {
    'print':Type.none_t,
    'range':Type.none_t,
    'len':Type.int_t,
    'write':Type.none_t,
    'display':Type.none_t,
    'assert':Type.none_t,
    'wait':Type.none_t,
    '$toprun':Type.none_t,
}
builtin_names = builtin_return_type_table.keys()

builtin_port_type_names = [
    'io.Bit',
    'io.Int',
    'io.Uint',
    'io.Fifo',
]
