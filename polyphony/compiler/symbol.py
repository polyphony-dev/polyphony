from .common import Tagged
from .env import env
from .type import Type
from logging import getLogger
logger = getLogger(__name__)


class Symbol(Tagged):
    __slots__ = ['id', 'name', 'scope', 'typ', 'ancestor']
    all_symbols = []

    TAGS = {
        'temp', 'param', 'return', 'condition', 'induction', 'alias',
        'self', 'static', 'subobject',
        'builtin', 'inlined', 'flattened', 'pipelined', 'predefined',
        'loop_counter'
    }

    @classmethod
    def unique_name(cls, prefix=None):
        if not prefix:
            prefix = cls.temp_prefix
        return '{}{}'.format(prefix, len(cls.all_symbols))

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

    return_prefix = '@function_return'
    condition_prefix = '@c'
    temp_prefix = '@t'
    param_prefix = '@in'

    def __init__(self, name, scope, tags, typ=Type.undef_t):
        super().__init__(tags)
        self.id = len(Symbol.all_symbols)
        self.name = name
        self.scope = scope
        self.typ = typ
        self.ancestor = None
        Symbol.all_symbols.append(self)

    def __str__(self):
        #return '{}:{}({}:{})'.format(self.name, self.typ, self.id, self.scope.orig_name)
        #return '{}:{}({})'.format(self.name, repr(self.typ), self.tags)
        if env.dev_debug_mode:
            return '{}:{}'.format(self.name, self.typ)
        return self.name

    def __repr__(self):
        #return '{}({})'.format(self.name, hex(self.__hash__()))
        return self.name

    def __lt__(self, other):
        return self.name < other.name

    def orig_name(self):
        if self.ancestor:
            return self.ancestor.orig_name()
        else:
            return self.name

    def root_sym(self):
        if self.ancestor:
            return self.ancestor.root_sym()
        else:
            return self

    def hdl_name(self):
        if self.typ.is_port():
            name = self.name[:]
        elif self.typ.is_object() and self.typ.get_scope().is_module() and self.ancestor:
            return self.ancestor.hdl_name()
        elif self.name[0] == '@' or self.name[0] == '!':
            name = self.name[1:]
        else:
            name = self.name[:]
        name = name.replace('#', '')
        return name

    def set_type(self, typ):
        if self.typ.is_freezed():
            assert False
        self.typ = typ
        if self.ancestor and not self.ancestor.typ.is_freezed():
            self.ancestor.set_type(typ.clone())

    def clone(self, scope, postfix=''):
        newsym = Symbol(self.name + postfix,
                        scope,
                        set(self.tags),
                        self.typ.clone())
        newsym.ancestor = self.ancestor
        return newsym
