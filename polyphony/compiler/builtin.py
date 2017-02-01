from .type import Type

builtin_return_type_table = {
    'print':Type.none_t,
    'range':Type.none_t,
    'len':Type.int_t,
    'write':Type.none_t,
    'display':Type.none_t,
    'assert':Type.none_t,
    '$toprun':Type.none_t,
}
builtin_names = builtin_return_type_table.keys()


lib_port_type_names = (
    'polyphony.io.Bit',
    'polyphony.io.Int',
    'polyphony.io.Uint',
    'polyphony.io.Queue',
)

lib_class_names = lib_port_type_names
