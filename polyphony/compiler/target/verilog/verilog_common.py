PYTHON_OP_2_VERILOG_OP_MAP = {
    'And': '&&', 'Or': '||',
    'Add': '+', 'Sub': '-', 'Mult': '*', 'FloorDiv': '/', 'Mod': '%',
    'LShift': '<<', 'RShift': '>>>',
    'BitOr': '|', 'BitXor': '^', 'BitAnd': '&',
    'Eq': '==', 'NotEq': '!=', 'Lt': '<', 'LtE': '<=', 'Gt': '>', 'GtE':'>=',
    'IsNot': '!=',
    'USub': '-', 'UAdd': '+', 'Not': '!', 'Invert':'~'
}


def pyop2verilogop(op):
    return PYTHON_OP_2_VERILOG_OP_MAP[op]


_keywords = {
    'always', 'assign', 'automatic',
    'begin',
    'case', 'casex', 'casez', 'cell', 'config',
    'deassign', 'default', 'defparam', 'design', 'disable',
    'edge', 'else', 'end', 'endcase', 'endconfig', 'endfunction', 'endgenerate',
    'endmodule', 'endprimitive', 'endspecify', 'endtable', 'endtask', 'event',
    'for', 'force', 'forever', 'fork', 'function',
    'generate', 'genvar',
    'if', 'ifnone', 'incdir', 'include', 'initial', 'inout', 'input', 'instance',
    'join', 'liblist', 'library', 'localparam',
    'macromodule', 'module',
    'negedge', 'noshowcancelled',
    'output',
    'parameter', 'posedge', 'primitive', 'pulsestyle_ondetect', 'pulsestyle_onevent',
    'reg', 'release', 'repeat',
    'scalared', 'showcancelled', 'signed', 'specparam', 'strength',
    'table', 'task', 'tri', 'tri0', 'tri1', 'triand', 'trior', 'trireg',
    'unsigned', 'use',
    'vectored',
    'wait', 'wand', 'while', 'wor', 'wire',
    # polyphony specific
    'clk', 'rst',
}


def is_verilog_keyword(word):
    return word in _keywords
