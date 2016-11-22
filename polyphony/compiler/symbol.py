from .type import Type
from logging import getLogger
logger = getLogger(__name__)

def function_name(t):
    assert t.name[0] == '!'
    return t.name[1:].split('#')[0]

class Symbol:
    all_symbols = []

    @classmethod
    def new(cls, name, scope):
        t = Symbol(name, scope, len(cls.all_symbols))
        cls.all_symbols.append(t)
        return t

    @classmethod
    def newtemp(cls, name, scope):
        id = len(cls.all_symbols)
        t = Symbol(name+str(id), scope, id)
        cls.all_symbols.append(t)
        return t

    @classmethod
    def dump(cls):
        logger.debug('All symbol instances ----------------')
        for sym in cls.all_symbols:
            s = str(sym) + '\n'
            s += '  defs\n'
            for d in sym.defs:
                s += '    ' + str(d) + '\n'
            s += '  uses\n'
            for u in sym.uses:
                s += '    ' + str(u) + '\n'
            logger.debug(s)

    func_prefix = '!'
    return_prefix = '@function_return'
    condition_prefix = '@cond'
    temp_prefix = '@t'
    param_prefix = '@in'
    field_prefix = '@f'
    port_prefix = '@p'
    ref_prefix = '@r'

    def __init__(self, name, scope, id):
        self.id = id
        self.name = name
        self.scope = scope
        self.typ = Type.none_t
        self.ancestor = None

    def __str__(self):
        return self.name + ':' + Type.str(self.typ) # + "_" + str(self.id)

    def __repr__(self):
        return '{}({})'.format(self.name, hex(self.__hash__()))

    def __lt__(self, other):
        return self.name < other.name
  
    def hdl_name(self):
        if self.name[0] == '@' or self.name[0] == '!':
            name = self.name[1:]
        else:
            name = self.name[:]
        name = name.replace('#', '')
        return name
   
    def is_function(self):
        return self.name[0] == Symbol.func_prefix

    def is_return(self):
        return self.name.startswith(Symbol.return_prefix)

    def is_condition(self):
        return self.name.startswith(Symbol.condition_prefix)

    def is_temp(self):
        return self.name.startswith(Symbol.temp_prefix)

    def is_param(self):
        return self.name.startswith(Symbol.param_prefix)

    def is_field(self):
        return self.name.startswith(Symbol.field_prefix)

    def is_port(self):
        return self.name.startswith(Symbol.port_prefix)

    def is_ref(self):
        return self.name.startswith(Symbol.ref_prefix)

    def set_type(self, typ):
        self.typ = typ
        if self.ancestor:
            self.ancestor.set_type(typ)

