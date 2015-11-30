PYTHON_OP_2_VERILOG_OP_MAP = {
    'And':'&&',
    'Or':'||',
    'Add':'+',
    'Sub':'-',
    'Mult':'*',
    'Div':'/',
    'LShift':'<<',
    'RShift':'>>',
    'BitOr':'|',
    'BitXor':'^',
    'BitAnd':'&',
    'Eq':'==',
    'NotEq':'!=',
    'Lt':'<',
    'LtE':'<=',
    'Gt':'>',
    'GtE':'>=',
    'IsNot':'!=',
    'USub':'-',
    'UAdd':'+',
    'Not':'!',
    'Invert':'~'
    }

def pyop2verilogop(op):
    return PYTHON_OP_2_VERILOG_OP_MAP[op]

