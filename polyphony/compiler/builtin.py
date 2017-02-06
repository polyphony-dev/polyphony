from .type import Type

builtin_return_type_table = {
    'print':Type.none_t,
    'range':Type.none_t,
    'len':Type.int(),
    'assert':Type.none_t,
    'polyphony.verilog.write':Type.none_t,
    'polyphony.verilog.display':Type.none_t,
    'polyphony.timing.clksleep':Type.none_t,
    'polyphony.timing.wait_rising':Type.none_t,
    'polyphony.timing.wait_falling':Type.none_t,
    'polyphony.timing.wait_value':Type.none_t,
    'polyphony.timing.wait_edge':Type.none_t,
}
builtin_names = builtin_return_type_table.keys()


lib_port_type_names = (
    'polyphony.io._DataPort',
    'polyphony.io.Bit',
    'polyphony.io.Int',
    'polyphony.io.Uint',
    'polyphony.io.Queue',
)

lib_class_names = lib_port_type_names
