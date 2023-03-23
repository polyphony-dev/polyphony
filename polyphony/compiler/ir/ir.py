from collections import namedtuple
from enum import IntEnum
from .symbol import Symbol
from ..common.utils import is_a, find_id_index


op2sym_map = {
    'And': 'and', 'Or': 'or',
    'Add': '+', 'Sub': '-', 'Mult': '*', 'FloorDiv': '//', 'Mod': '%',
    'LShift': '<<', 'RShift': '>>',
    'BitOr': '|', 'BitXor': '^', 'BitAnd': '&',
    'Eq': '==', 'NotEq': '!=', 'Lt': '<', 'LtE': '<=', 'Gt': '>', 'GtE': '>=',
    'IsNot': '!=',
    'USub': '-', 'UAdd': '+', 'Not': '!', 'Invert': '~'
}


class Ctx(IntEnum):
    LOAD = 1
    STORE = 2
    CALL = 3

Loc = namedtuple('Loc', ('filename', 'lineno'))


class IR(object):
    def __init__(self):
        pass

    def __repr__(self):
        return self.__str__()

    def __hash__(self):
        return super().__hash__()

    def __lt__(self, other):
        return hash(self) < hash(other)

    def is_a(self, cls):
        return is_a(self, cls)

    def clone(self, **args):
        clone = self.__new__(self.__class__)
        clone.__dict__ = self.__dict__.copy()
        for k, v in clone.__dict__.items():
            if isinstance(v, IR):
                clone.__dict__[k] = v.clone()
            elif isinstance(v, list):
                li = []
                for elm in v:
                    if isinstance(elm, IR):
                        li.append(elm.clone())
                    else:
                        li.append(elm)
                clone.__dict__[k] = li
        for k, v in args.items():
            if ('_' + k) in clone.__dict__:
                clone.__dict__[('_' + k)] = v
        return clone

    def replace(self, old, new):
        def replace_rec(ir, old, new):
            if isinstance(ir, IR):
                if ir.is_a([CALL, SYSCALL, NEW]):
                    return ir.replace(old, new)
                ret = False
                for k, v in ir.__dict__.items():
                    if v == old:
                        ir.__dict__[k] = new
                        ret = True
                    elif replace_rec(v, old, new):
                        ret = True
                return ret
            elif isinstance(ir, list):
                ret = False
                for i, elm in enumerate(ir):
                    if elm == old:
                        ir[i] = new
                        ret = True
                    elif replace_rec(elm, old, new):
                        ret = True
                return ret
            return False
        return replace_rec(self, old, new)

    def find_vars(self, qsym):
        vars = []

        def find_vars_rec(ir, qsym, vars):
            if isinstance(ir, IR):
                if ir.is_a([CALL, SYSCALL, NEW]):
                    vars.extend(ir.find_vars(qsym))
                elif ir.is_a(TEMP):
                    if ir.qualified_symbol == qsym:
                        vars.append(ir)
                elif ir.is_a(ATTR):
                    if ir.qualified_symbol == qsym:
                        vars.append(ir)
                    else:
                        find_vars_rec(ir.exp, qsym, vars)
                else:
                    for k, v in ir.__dict__.items():
                        find_vars_rec(v, qsym, vars)
            elif isinstance(ir, list) or isinstance(ir, tuple):
                for elm in ir:
                    find_vars_rec(elm, qsym, vars)
        find_vars_rec(self, qsym, vars)
        return vars

    def find_irs(self, typ):
        irs = []

        def find_irs_rec(ir, typ, irs):
            if isinstance(ir, IR):
                if ir.is_a(typ):
                    irs.append(ir)
                if ir.is_a([CALL, SYSCALL, NEW]):
                    irs.extend(ir.find_irs(typ))
                    return
                for k, v in ir.__dict__.items():
                    find_irs_rec(v, typ, irs)
            elif isinstance(ir, list) or isinstance(ir, tuple):
                for elm in ir:
                    find_irs_rec(elm, typ, irs)
        find_irs_rec(self, typ, irs)
        return irs


class IRExp(IR):
    def __init__(self):
        super().__init__()


class UNOP(IRExp):
    def __init__(self, op, exp):
        assert op in {'USub', 'UAdd', 'Not', 'Invert'}
        super().__init__()
        self._op = op
        self._exp = exp

    def __str__(self):
        return '{}{}'.format(op2sym_map[self._op], self._exp)

    def __eq__(self, other):
        if other is None or not isinstance(other, UNOP):
            return False
        return self._op == other._op and self._exp == other._exp

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        return self._exp.kids()

    @property
    def op(self):
        return self._op

    @property
    def exp(self):
        return self._exp

    @exp.setter
    def exp(self, exp):
        self._exp = exp


class BINOP(IRExp):
    def __init__(self, op, left, right):
        assert op in {
            'Add', 'Sub', 'Mult', 'FloorDiv', 'Mod',
            'LShift', 'RShift',
            'BitOr', 'BitXor', 'BitAnd',
        }
        super().__init__()
        self._op = op
        self._left = left
        self._right = right

    def __str__(self):
        return '({} {} {})'.format(self._left, op2sym_map[self._op], self._right)

    def __eq__(self, other):
        if other is None or not isinstance(other, BINOP):
            return False
        return (self._op == other._op and self._left == other._left and self._right == other._right)

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        return self._left.kids() + self._right.kids()

    @property
    def op(self):
        return self._op

    @property
    def left(self):
        return self._left

    @left.setter
    def left(self, exp):
        self._left = exp

    @property
    def right(self):
        return self._right

    @right.setter
    def right(self, exp):
        self._right = exp


class RELOP(IRExp):
    def __init__(self, op, left, right):
        assert op in {
            'And', 'Or',
            'Eq', 'NotEq', 'Lt', 'LtE', 'Gt', 'GtE',
            'IsNot',
        }
        super().__init__()
        self._op = op
        self._left = left
        self._right = right

    def __str__(self):
        return '({} {} {})'.format(self._left, op2sym_map[self._op], self._right)

    def __eq__(self, other):
        if other is None or not isinstance(other, RELOP):
            return False
        return (self._op == other._op and self._left == other._left and self._right == other._right)

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        return self._left.kids() + self._right.kids()

    @property
    def op(self):
        return self._op

    @property
    def left(self):
        return self._left

    @left.setter
    def left(self, exp):
        self._left = exp

    @property
    def right(self):
        return self._right

    @right.setter
    def right(self, exp):
        self._right = exp


class CONDOP(IRExp):
    def __init__(self, cond, left, right):
        super().__init__()
        self._cond = cond
        self._left = left
        self._right = right

    def __str__(self):
        return '({} ? {} : {})'.format(self._cond, self._left, self._right)

    def __eq__(self, other):
        if other is None or not isinstance(other, CONDOP):
            return False
        return (self._cond == other._cond and self._left == other._left and self._right == other._right)

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        return self._cond.kids() + self._left.kids() + self._right.kids()

    @property
    def cond(self):
        return self._cond

    @cond.setter
    def cond(self, exp):
        self._cond = exp

    @property
    def left(self):
        return self._left

    @left.setter
    def left(self, exp):
        self._left = exp

    @property
    def right(self):
        return self._right

    @right.setter
    def right(self, exp):
        self._right = exp


class POLYOP(IRExp):
    def __init__(self, op, values):
        self._op = op
        self._values = values

    def __str__(self):
        values = ', '.join([str(e) for e in self._values])
        return '({} [{}])'.format(op2sym_map[self._op], values)

    def kids(self):
        assert all([v.is_a([CONST, TEMP, ATTR]) for v in self._values])
        return self._values

    @property
    def op(self):
        return self._op

    @property
    def values(self):
        return self._values


def replace_args(args, old, new):
    ret = False
    for i, (name, arg) in enumerate(args):
        if arg == old:
            args[i] = (name, new)
            ret = True
        if arg.replace(old, new):
            ret = True
    return ret


def find_vars_args(args, qsym):
    vars = []
    for _, arg in args:
        if arg.is_a([TEMP, ATTR]) and arg.qualified_symbol == qsym:
            vars.append(arg)
        vars.extend(arg.find_vars(qsym))
    return vars


def find_irs_args(args, typ):
    irs = []
    for _, arg in args:
        if arg.is_a(typ):
            irs.append(arg)
        irs.extend(arg.find_irs(typ))
    return irs


class IRCallable(IRExp):
    @property
    def callee_scope(self):
        if isinstance(self.symbol, str):
            print('!')
        func_t = self.symbol.typ
        assert func_t.has_scope()
        return func_t.scope


class CALL(IRCallable):
    def __init__(self, func, args, kwargs):
        super().__init__()
        assert isinstance(func, (TEMP, ATTR))
        self._func = func
        self._func._ctx = Ctx.CALL
        self._args = args
        self._kwargs = kwargs

    def __str__(self):
        s = '{}('.format(self._func)
        #s += ', '.join(['{}={}'.format(name, arg) for name, arg in self.args])
        s += ', '.join(['{}'.format(arg) for name, arg in self._args])
        if self._kwargs:
            s += ', '
            s += ', '.join([f'{name}={value}' for name, value in self._kwargs.items()])
        s += ")"
        return s

    def __eq__(self, other):
        if other is None or not isinstance(other, CALL):
            return False
        return (self._func == other._func and
                len(self._args) == len(other._args) and
                all([name == other_name and a == other_a
                     for (name, a), (other_name, other_a) in zip(self._args, other._args)]))

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        kids = []
        kids += self._func.kids()
        for _, arg in self._args:
            kids += arg.kids()
        return kids

    def clone(self):
        func = self._func.clone()
        args = [(name, arg.clone()) for name, arg in self._args]
        kwargs = {name:arg.clone() for name, arg in self._kwargs.items()}
        clone = CALL(func, args, kwargs)
        return clone

    def replace(self, old, new):
        if self._func is old:
            self._func = new
            return True
        if self._func.replace(old, new):
            return True
        if replace_args(self._args, old, new):
            return True
        for name, kwarg in self._kwargs.copy().items():
            if kwarg is old:
                self._kwargs[name] = new
                return True
            if kwarg.replace(old, new):
                return True
        return False

    def find_vars(self, qsym):
        vars = self._func.find_vars(qsym)
        vars.extend(find_vars_args(self._args, qsym))
        vars.extend(find_vars_args(self._kwargs.values(), qsym))
        return vars

    def find_irs(self, typ):
        irs = self._func.find_irs(typ)
        irs.extend(find_irs_args(self._args, typ))
        irs.extend(find_irs_args(self._kwargs.values(), typ))
        return irs

    @property
    def symbol(self):
        return self._func.symbol

    @property
    def qualified_symbol(self):
        return self._func.qualified_symbol

    @property
    def func(self):
        return self._func

    @func.setter
    def func(self, f):
        assert isinstance(f, (TEMP, ATTR))
        if f.ctx != Ctx.CALL:
            f._ctx = Ctx.CALL
        self._func = f

    @property
    def args(self):
        return self._args

    @args.setter
    def args(self, args):
        self._args = args

    @property
    def kwargs(self):
        return self._kwargs


class SYSCALL(IRCallable):
    def __init__(self, sym, args, kwargs):
        super().__init__()
        self._sym = sym
        self._args = args
        self._kwargs = kwargs

    def __str__(self):
        s = '!{}('.format(self._sym)
        #s += ', '.join(['{}={}'.format(name, arg) for name, arg in self.args])
        s += ', '.join(['{}'.format(arg) for name, arg in self._args])
        if self._kwargs:
            s += ', '
            s += ', '.join([f'{name}={value}' for name, value in self._kwargs.items()])
        s += ")"
        return s

    def __eq__(self, other):
        if other is None or not isinstance(other, SYSCALL):
            return False
        return (self._sym is other._sym and
                len(self._args) == len(other._args) and
                all([name == other_name and a == other_a
                     for (name, a), (other_name, other_a) in zip(self._args, other._args)]))

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        kids = []
        for _, arg in self._args:
            kids += arg.kids()
        return kids

    def clone(self):
        args = [(name, arg.clone()) for name, arg in self._args]
        kwargs = {name:arg.clone() for name, arg in self._kwargs.items()}
        clone = SYSCALL(self._sym, args, kwargs)
        return clone

    def replace(self, old, new):
        return replace_args(self._args, old, new)

    def find_vars(self, qsym):
        return find_vars_args(self._args, qsym)

    def find_irs(self, typ):
        return find_irs_args(self._args, typ)

    @property
    def symbol(self):
        return self._sym

    @property
    def qualified_symbol(self):
        return (self._sym, )

    @property
    def args(self):
        return self._args

    @args.setter
    def args(self, args):
        self._args = args

    @property
    def kwargs(self):
        return self._kwargs


class NEW(IRCallable):
    def __init__(self, sym, args, kwargs):
        super().__init__()
        self._sym = sym
        self._args = args
        self._kwargs = kwargs

    def __str__(self):
        s = '{}('.format(self._sym)
        s += ', '.join(['{}={}'.format(name, arg) for name, arg in self._args])
        if self._kwargs:
            s += ', '
            s += ', '.join([f'{name}={value}' for name, value in self._kwargs.items()])
        s += ")"
        return s

    def __eq__(self, other):
        if other is None or not isinstance(other, NEW):
            return False
        return (self._sym is other._sym and
                len(self._args) == len(other._args) and
                all([name == other_name and a == other_a
                     for (name, a), (other_name, other_a) in zip(self._args, other._args)]))

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        kids = []
        for _, arg in self._args:
            kids += arg.kids()
        return kids

    def clone(self):
        args = [(name, arg.clone()) for name, arg in self._args]
        kwargs = {name:arg.clone() for name, arg in self._kwargs.items()}
        clone = NEW(self._sym, args, kwargs)
        return clone

    def replace(self, old, new):
        return replace_args(self._args, old, new)

    def find_vars(self, qsym):
        return find_vars_args(self._args, qsym)

    def find_irs(self, typ):
        return find_irs_args(self._args, typ)

    @property
    def symbol(self):
        return self._sym

    @symbol.setter
    def symbol(self, sym):
        self._sym = sym

    @property
    def qualified_symbol(self):
        return (self._sym, )

    @property
    def args(self):
        return self._args

    @args.setter
    def args(self, args):
        self._args = args

    @property
    def kwargs(self):
        return self._kwargs


class CONST(IRExp):
    def __init__(self, value):
        super().__init__()
        self._value = value

    def __str__(self):
        if isinstance(self._value, bool):
            return str(self._value)
        elif isinstance(self._value, int):
            return hex(self._value)
        else:
            return repr(self._value)

    def __eq__(self, other):
        if other is None or not isinstance(other, CONST):
            return False
        return self._value == other._value

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        return [self]

    @property
    def value(self):
        return self._value


class MREF(IRExp):
    def __init__(self, mem, offset, ctx=Ctx.LOAD):
        super().__init__()
        assert mem.is_a([TEMP, ATTR, MREF])
        self._mem = mem
        self._offset = offset
        self._ctx = ctx

    def __str__(self):
        return '{}[{}]'.format(self._mem, self._offset)

    def __eq__(self, other):
        if other is None or not isinstance(other, MREF):
            return False
        return (self._mem == other._mem and self._offset == other._offset and self._ctx == other._ctx)

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        return self._mem.kids() + self._offset.kids()

    @property
    def ctx(self):
        return self._ctx

    @property
    def mem(self):
        return self._mem

    @mem.setter
    def mem(self, mem):
        self._mem = mem

    @property
    def offset(self):
        return self._offset

    @offset.setter
    def offset(self, offset):
        self._offset = offset


class MSTORE(IRExp):
    def __init__(self, mem, offset, exp):
        super().__init__()
        self._mem = mem
        self._offset = offset
        self._exp = exp

    def __str__(self):
        return 'mstore({}[{}], {})'.format(self._mem, self._offset, self._exp)

    def __eq__(self, other):
        if other is None or not isinstance(other, MSTORE):
            return False
        return (self._mem == other._mem and self._offset == other._offset and self._exp == other._exp)

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        return self._mem.kids() + self._offset.kids() + self._exp.kids()

    @property
    def mem(self):
        return self._mem

    @mem.setter
    def mem(self, mem):
        self._mem = mem

    @property
    def offset(self):
        return self._offset

    @offset.setter
    def offset(self, offset):
        self._offset = offset

    @property
    def exp(self):
        return self._exp

    @exp.setter
    def exp(self, e):
        self._exp = e


class ARRAY(IRExp):
    def __init__(self, items, is_mutable=True, sym=None):
        super().__init__()
        self._items = items
        self._sym = sym
        self._repeat = CONST(1)
        self._is_mutable = is_mutable

    def __str__(self):
        s = '[' if self._is_mutable else '('
        if len(self._items) > 8:
            s += ', '.join(map(str, self._items[:10]))
            s += '...'
        else:
            s += ', '.join(map(str, self._items))
        s += ']' if self._is_mutable else ')'
        if not (self._repeat.is_a(CONST) and self._repeat.value == 1):
            s += ' * ' + str(self._repeat)
        return s

    def __eq__(self, other):
        if other is None or not isinstance(other, ARRAY):
            return False
        return (len(self._items) == len(other._items) and
                all([item == other_item for item, other_item in zip(self._items, other._items)]) and
                self._sym is other._sym and
                self._repeat == other._repeat and
                self._is_mutable == other._is_mutable)

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        kids = []
        for item in self._items:
            kids += item.kids()
        return kids

    def getlen(self):
        if self._repeat.is_a(CONST):
            return len(self._items) * self._repeat.value
        else:
            return -1

    @property
    def symbol(self):
        return self._sym

    @symbol.setter
    def symbol(self, sym):
        self._sym = sym

    @property
    def qualified_symbol(self):
        return (self._sym, )

    @property
    def items(self):
        return self._items

    @items.setter
    def items(self, items):
        self._items = items

    @property
    def repeat(self):
        return self._repeat

    @repeat.setter
    def repeat(self, repeat):
        self._repeat = repeat

    @property
    def is_mutable(self):
        return self._is_mutable


class TEMP(IRExp):
    def __init__(self, sym, ctx=Ctx.LOAD):
        super().__init__()
        assert isinstance(sym, Symbol)
        assert isinstance(ctx, int)
        self._sym = sym
        self._ctx = ctx

    def __str__(self):
        return str(self._sym)

    def __eq__(self, other):
        if other is None or not isinstance(other, TEMP):
            return False
        return (self._sym is other._sym and self._ctx == other._ctx)

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        return [self]

    @property
    def symbol(self):
        return self._sym

    @symbol.setter
    def symbol(self, sym):
        self._sym = sym

    @property
    def qualified_symbol(self):
        return (self._sym, )

    @property
    def ctx(self):
        return self._ctx


class ATTR(IRExp):
    def __init__(self, exp, attr, ctx=Ctx.LOAD):
        super().__init__()
        self._exp = exp
        self._attr = attr
        self._ctx = ctx
        self._exp._ctx = Ctx.LOAD

    def __str__(self):
        return '{}->{}'.format(self.exp, self._attr)

    def __eq__(self, other):
        if other is None or not isinstance(other, ATTR):
            return False
        return (self._exp == other._exp and
                self._attr is other._attr and
                self._ctx == other._ctx)

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        return [self]

    # a.b.c.d = (((a.b).c).d)
    #              |    |
    #             head  |
    #                  tail
    def head(self):
        if self._exp.is_a(ATTR):
            return self._exp.head()
        elif self._exp.is_a(TEMP):
            return self._exp.symbol
        else:
            return None

    def tail(self):
        return self._exp.symbol

    @property
    def symbol(self):
        return self._attr

    @symbol.setter
    def symbol(self, sym):
        self._attr = sym

    @property
    def qualified_symbol(self):
        return self._exp.qualified_symbol + (self._attr,)

    @property
    def ctx(self):
        return self._ctx

    def replace_head(self, new_head):
        if self._exp.is_a(ATTR):
            self._exp.replace_head(new_head)
        else:
            self._exp.symbol = new_head
        return self

    @property
    def exp(self):
        return self._exp

    @exp.setter
    def exp(self, e):
        self._exp = e


class IRStm(IR):
    def __init__(self, loc):
        super().__init__()
        if not loc:
            self.loc = Loc('', 0)
        else:
            self.loc = loc
        self.block = None

    def program_order(self):
        return (self.block.order, find_id_index(self.block.stms, self))

    def kids(self):
        return []

    def is_mem_read(self):
        return self.is_a(MOVE) and self.src.is_a(MREF)

    def is_mem_write(self):
        return self.is_a(EXPR) and self.exp.is_a(MSTORE)


class EXPR(IRStm):
    def __init__(self, exp, loc=None):
        super().__init__(loc)
        self._exp = exp

    def __str__(self):
        return '{}'.format(self._exp)

    def __eq__(self, other):
        if other is None or not isinstance(other, EXPR):
            return False
        return self._exp == other._exp

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        return self._exp.kids()

    @property
    def exp(self):
        return self._exp

    @exp.setter
    def exp(self, e):
        self._exp = e


class CJUMP(IRStm):
    def __init__(self, exp, true, false, loc=None):
        super().__init__(loc)
        self._exp = exp
        self._true = true
        self._false = false
        self._loop_branch = False

    def __str__(self):
        return 'cjump {} ? {}, {}'.format(self._exp, self._true.name, self._false.name)

    def __eq__(self, other):
        if other is None or not isinstance(other, CJUMP):
            return False
        return self._exp == other._exp and self._true is other._true and self._false is other._false

    def __hash__(self):
        return super().__hash__()

    @property
    def exp(self):
        return self._exp

    @exp.setter
    def exp(self, e):
        self._exp = e

    @property
    def true(self):
        return self._true

    @true.setter
    def true(self, t):
        self._true = t

    @property
    def false(self):
        return self._false

    @false.setter
    def false(self, f):
        self._false = f

    @property
    def loop_branch(self):
        return self._loop_branch

    @loop_branch.setter
    def loop_branch(self, l):
        self._loop_branch = l


class MCJUMP(IRStm):
    def __init__(self, loc=None):
        super().__init__(loc)
        self._conds = []
        self._targets = []
        self._loop_branch = False

    def __str__(self):
        assert len(self._conds) == len(self._targets)
        items = []
        for cond, target in zip(self._conds, self._targets):
            items.append('{} ? {}'.format(cond, target.name))

        return 'mcjump(\n        {})'.format(', \n        '.join([item for item in items]))

    def __eq__(self, other):
        if other is None or not isinstance(other, MCJUMP):
            return False
        return (len(self._conds) == len(other._conds) and
                all([cond == other_cond for cond, other_cond in zip(self._conds, other._conds)]) and
                all([target is other_target for target, other_target in zip(self._targets, other._targets)]))

    def __hash__(self):
        return super().__hash__()

    @property
    def conds(self):
        return self._conds

    @conds.setter
    def conds(self, c):
        self._conds = c

    @property
    def targets(self):
        return self._targets

    @targets.setter
    def targets(self, t):
        self._targets = t

    @property
    def loop_branch(self):
        return self._loop_branch

    @loop_branch.setter
    def loop_branch(self, l):
        self._loop_branch = l


class JUMP(IRStm):
    def __init__(self, target, typ='', loc=None):
        super().__init__(loc)
        self._target = target
        self._typ = typ  # 'B': break, 'C': continue, 'L': loop-back, 'S': specific

    def __str__(self):
        return "jump {} '{}'".format(self._target.name, self._typ)

    def __eq__(self, other):
        if other is None or not isinstance(other, JUMP):
            return False
        return self._target is other._target

    def __hash__(self):
        return super().__hash__()

    @property
    def target(self):
        return self._target

    @target.setter
    def target(self, t):
        self._target = t

    @property
    def typ(self):
        return self._typ

    @typ.setter
    def typ(self, t):
        self._typ = t


class RET(IRStm):
    def __init__(self, exp, loc=None):
        super().__init__(loc)
        self._exp = exp

    def __str__(self):
        return "return {}".format(self._exp)

    def __eq__(self, other):
        if other is None or not isinstance(other, RET):
            return False
        return self._exp == other._exp

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        return self._exp.kids()

    @property
    def exp(self):
        return self._exp

    @exp.setter
    def exp(self, e):
        self._exp = e


class MOVE(IRStm):
    def __init__(self, dst, src, loc=None):
        super().__init__(loc)
        self._dst = dst
        self._src = src

    def __str__(self):
        return '{} = {}'.format(self._dst, self._src)

    def __eq__(self, other):
        if other is None or not isinstance(other, MOVE):
            return False
        return self._dst == other._dst and self._src == other._src

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        return self._dst.kids() + self._src.kids()

    @property
    def src(self):
        return self._src

    @src.setter
    def src(self, src):
        self._src = src

    @property
    def dst(self):
        return self._dst

    @dst.setter
    def dst(self, dst):
        self._dst = dst


class CEXPR(EXPR):
    def __init__(self, cond, exp, loc=None):
        super().__init__(exp, loc)
        assert isinstance(cond, IRExp)
        self._cond = cond

    def __str__(self):
        return "{} ? {}".format(self._cond, super().__str__())

    def __eq__(self, other):
        if other is None or not isinstance(other, CEXPR):
            return False
        return self._cond == other._cond and super().__eq__(other)

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        return self._cond.kids() + super().kids()

    @property
    def cond(self):
        return self._cond

    @cond.setter
    def cond(self, c):
        self._cond = c


class CMOVE(MOVE):
    def __init__(self, cond, dst, src, loc=None):
        super().__init__(dst, src, loc)
        assert isinstance(cond, IRExp)
        self._cond = cond

    def __str__(self):
        return "{} ? {}".format(self._cond, super().__str__())

    def __eq__(self, other):
        if other is None or not isinstance(other, CEXPR):
            return False
        return self._cond == other._cond and super().__eq__(other)

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        return self._cond.kids() + super().kids()

    @property
    def cond(self):
        return self._cond

    @cond.setter
    def cond(self, c):
        self._cond = c


def conds2str(conds):
    if conds:
        cs = []
        for exp, boolean in conds:
            cs.append(str(exp) + ' == ' + str(boolean))
        return ' and '.join(cs)
    else:
        return 'None'


class PHIBase(IRStm):
    def __init__(self, var):
        super().__init__(loc=None)
        assert var.is_a([TEMP, ATTR])
        self._var = var
        self._var._ctx = Ctx.STORE
        self._args = []
        self._ps = []

    def _str_args(self, with_p=True):
        str_args = []
        if self._ps and with_p:
            #assert len(self.ps) == len(self.args)
            for arg, p in zip(self._args, self._ps):
                if arg:
                    str_args.append('{} ? {}'.format(p, arg))
                else:
                    str_args.append('_')
        else:
            for arg in self._args:
                if arg:
                    str_args.append('{}'.format(arg))
                else:
                    str_args.append('_')
        return str_args

    def __eq__(self, other):
        if other is None or not isinstance(other, PHIBase):
            return False
        return self._var == other._var

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        kids = []
        for arg in self._args:
            kids += arg.kids()
        return self._var.kids() + kids

    def remove_arg(self, arg):
        idx = find_id_index(self._args, arg)
        if self._ps:
            assert len(self._args) == len(self._ps)
            self._ps.pop(idx)
        self._args.pop(idx)

    def reorder_args(self, indices):
        args = []
        ps = []
        for idx in indices:
            assert 0 <= idx < len(self._args)
            args.append(self._args[idx])
            ps.append(self._ps[idx])
        self._args = args
        self._ps = ps

    @property
    def var(self):
        return self._var

    @var.setter
    def var(self, var):
        self._var = var

    @property
    def args(self):
        return self._args

    @args.setter
    def args(self, args):
        self._args = args

    @property
    def ps(self):
        return self._ps

    @ps.setter
    def ps(self, ps):
        self._ps = ps


class PHI(PHIBase):
    def __init__(self, var):
        super().__init__(var)

    def __str__(self):
        if len(self._args) >= 2:
            delim = ',\n        '
        else:
            delim = ', '
        if self.block.is_hyperblock:
            s = "{} = psi({})".format(self._var, delim.join(self._str_args()))
        else:
            s = "{} = phi({})".format(self._var, delim.join(self._str_args()))
        return s


class UPHI(PHIBase):
    def __init__(self, var):
        super().__init__(var)

    def __str__(self):
        s = "{} = uphi({})".format(self._var, ", ".join(self._str_args()))
        return s


class LPHI(PHIBase):
    def __init__(self, var):
        super().__init__(var)

    def __str__(self):
        s = "{} = lphi({})".format(self._var, ", ".join(self._str_args()))
        return s

    @classmethod
    def from_phi(cls, phi):
        lphi = LPHI(phi._var.clone())
        lphi._args = phi._args[:]
        lphi._ps = [CONST(1)] * len(phi._ps)
        lphi.block = phi.block
        lphi.loc = phi.loc
        return lphi


class MSTM(IRStm):
    def __init__(self, loc=None):
        super().__init__(loc)
        self._stms = []

    def append(self, stm):
        self._stms.append(stm)

    def __str__(self):
        return 'mstm{{{}}}'.format(', '.join([str(stm) for stm in self._stms]))

    def __eq__(self, other):
        if other is None or not isinstance(other, MSTM):
            return False
        return all([a == b for a, b in zip(self._stms, other._stms)])

    def __hash__(self):
        return super().__hash__()

    @property
    def stms(self):
        return self._stms

