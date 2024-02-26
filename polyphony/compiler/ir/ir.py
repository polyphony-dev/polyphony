from __future__ import annotations
import typing
from typing import cast, TYPE_CHECKING
from collections import namedtuple
from enum import IntEnum
from .symbol import Symbol
from .types.scopetype import ScopeType
from ..common.utils import is_a, find_id_index
if TYPE_CHECKING:
    from .scope import Scope


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

    def type_str(self, scope: Scope):
        return ''

    def is_a(self, cls):
        return is_a(self, cls)

    def as_a[T](self, cls:T) -> T | None:
        if is_a(self, cls):
            return cast(T, self)
        else:
            return None

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
                        # TODO: remove this block
                        if k == '_sym':
                            ir.__dict__['_name'] = new.name
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

    def find_vars(self, qname: tuple[str, ...]):
        assert len(qname) > 0 and isinstance(qname[0], str)
        vars = []

        def find_vars_rec(ir, qname, vars):
            if isinstance(ir, IR):
                if ir.is_a([CALL, SYSCALL, NEW]):
                    vars.extend(ir.find_vars(qname))
                elif ir.is_a(TEMP):
                    temp = cast(TEMP, ir)
                    if temp.qualified_name == qname:
                        vars.append(ir)
                elif ir.is_a(ATTR):
                    attr = cast(ATTR, ir)
                    if attr.qualified_name == qname:
                        vars.append(ir)
                    else:
                        find_vars_rec(attr.exp, qname, vars)
                else:
                    for k, v in ir.__dict__.items():
                        find_vars_rec(v, qname, vars)
            elif isinstance(ir, list) or isinstance(ir, tuple):
                for elm in ir:
                    find_vars_rec(elm, qname, vars)
        find_vars_rec(self, qname, vars)
        return vars

    def find_irs(self, typ: typing.Type):
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


class IRNameExp(IRExp):
    def __init__(self, name: str):
        super().__init__()
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, name):
        self._name = name

    @property
    def qualified_name(self) -> tuple[str, ...]:
        return (self.name,)


class UNOP(IRExp):
    def __init__(self, op: str, exp: IRExp):
        assert op in {'USub', 'UAdd', 'Not', 'Invert'}
        super().__init__()
        self._op = op
        self._exp = exp

    def __str__(self):
        return f'{op2sym_map[self._op]}{self._exp}'

    def type_str(self, scope: Scope):
        return f'{op2sym_map[self._op]}{self._exp.type_str(scope)}'

    def __eq__(self, other):
        if other is None or not isinstance(other, UNOP):
            return False
        return self._op == other._op and self._exp == other._exp

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        return self._exp.kids()

    @property
    def op(self) -> str:
        return self._op

    @property
    def exp(self) -> IRExp:
        return self._exp

    @exp.setter
    def exp(self, exp):
        self._exp = exp


class BINOP(IRExp):
    def __init__(self, op: str, left: IRExp, right: IRExp):
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
        return f'({self._left} {op2sym_map[self._op]} {self._right})'

    def type_str(self, scope: Scope):
        return f'({self._left.type_str(scope)} {op2sym_map[self._op]} {self._right.type_str(scope)})'

    def __eq__(self, other):
        if other is None or not isinstance(other, BINOP):
            return False
        return (self._op == other._op and self._left == other._left and self._right == other._right)

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        return self._left.kids() + self._right.kids()

    @property
    def op(self) -> str:
        return self._op

    @property
    def left(self) -> IRExp:
        return self._left

    @left.setter
    def left(self, exp):
        self._left = exp

    @property
    def right(self) -> IRExp:
        return self._right

    @right.setter
    def right(self, exp):
        self._right = exp


class RELOP(IRExp):
    def __init__(self, op: str, left: IRExp, right: IRExp):
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
        return f'({self._left} {op2sym_map[self._op]} {self._right})'

    def type_str(self, scope: Scope):
        return f'({self._left.type_str(scope)} {op2sym_map[self._op]} {self._right.type_str(scope)})'

    def __eq__(self, other):
        if other is None or not isinstance(other, RELOP):
            return False
        return (self._op == other._op and self._left == other._left and self._right == other._right)

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        return self._left.kids() + self._right.kids()

    @property
    def op(self) -> str:
        return self._op

    @property
    def left(self) -> IRExp:
        return self._left

    @left.setter
    def left(self, exp):
        self._left = exp

    @property
    def right(self) -> IRExp:
        return self._right

    @right.setter
    def right(self, exp):
        self._right = exp


class CONDOP(IRExp):
    def __init__(self, cond: IRExp, left: IRExp, right: IRExp):
        super().__init__()
        self._cond = cond
        self._left = left
        self._right = right

    def __str__(self):
        return f'({self._cond} ? {self._left} : {self._right})'

    def type_str(self, scope: Scope):
        return f'({self._cond.type_str(scope)} ? {self._left.type_str(scope)} : {self._right.type_str(scope)})'

    def __eq__(self, other):
        if other is None or not isinstance(other, CONDOP):
            return False
        return (self._cond == other._cond and self._left == other._left and self._right == other._right)

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        return self._cond.kids() + self._left.kids() + self._right.kids()

    @property
    def cond(self) -> IRExp:
        return self._cond

    @cond.setter
    def cond(self, exp):
        self._cond = exp

    @property
    def left(self) -> IRExp:
        return self._left

    @left.setter
    def left(self, exp):
        self._left = exp

    @property
    def right(self) -> IRExp:
        return self._right

    @right.setter
    def right(self, exp):
        self._right = exp


class POLYOP(IRExp):
    def __init__(self, op: str, values: list[IRExp]):
        self._op = op
        self._values = values

    def __str__(self):
        values = ', '.join([str(e) for e in self._values])
        return f'({op2sym_map[self._op]} [{values}])'

    def type_str(self, scope: Scope):
        values = ', '.join([e.type_str(scope) for e in self._values])
        return f'({op2sym_map[self._op]} [{values}])'

    def kids(self):
        assert all([v.is_a([CONST, TEMP, ATTR]) for v in self._values])
        return self._values

    @property
    def op(self) -> str:
        return self._op

    @property
    def values(self) -> list[IRExp]:
        return self._values


def replace_args(args: list[tuple[str, IRExp]], old: IRExp, new: IRExp):
    ret = False
    for i, (name, arg) in enumerate(args):
        if arg == old:
            args[i] = (name, new)
            ret = True
        if arg.replace(old, new):
            ret = True
    return ret


def find_vars_args(args: list[tuple[str, IRExp]], qname: tuple[str, ...]) -> list[IRExp]:
    vars = []
    for _, arg in args:
        if ((v := arg.as_a(TEMP)) or (v := arg.as_a(ATTR))) and v.qualified_name == qname:
            vars.append(arg)
        vars.extend(arg.find_vars(qname))
    return vars


def find_irs_args(args: list[tuple[str, IRExp]], typ: typing.Type) -> list[IRExp]:
    irs = []
    for _, arg in args:
        if arg.is_a(typ):
            irs.append(arg)
        irs.extend(arg.find_irs(typ))
    return irs


class IRCallable(IRNameExp):
    def __init__(self, func:IRVariable, args:list[tuple[str, IRExp]], kwargs:dict[str, IRExp]):
        assert isinstance(func, IRVariable)
        super().__init__('')
        self._func = func
        self._func.ctx = Ctx.CALL
        self._args = args
        self._kwargs = kwargs

    def type_str(self, scope: Scope):
        s = f'{self._func.type_str(scope)}('
        s += ', '.join([arg.type_str(scope) for name, arg in self._args])
        if self._kwargs:
            s += ', '
            s += ', '.join([f'{name}={value.type_str(scope)}' for name, value in self._kwargs.items()])
        s += ")"
        return s

    def __eq__(self, other):
        if other is None or not isinstance(other, IRCallable):
            return False
        return (self._func == other._func and
                len(self._args) == len(other._args) and
                all([name == other_name and a == other_a
                     for (name, a), (other_name, other_a) in zip(self._args, other._args)]))

    def __hash__(self):
        return super().__hash__()

    @property
    def name(self) -> str:
        return self._func.name

    @name.setter
    def name(self, name):
        self._func.name = name

    @property
    def qualified_name(self) -> tuple[str, ...]:
        return self.func.qualified_name

    @property
    def func(self):
        return self._func

    @func.setter
    def func(self, f):
        assert isinstance(f, IRVariable)
        if f.ctx != Ctx.CALL:
            f.ctx = Ctx.CALL
        self._func = f

    @property
    def args(self) -> list[tuple[str, IRExp]]:
        return self._args

    @args.setter
    def args(self, args):
        self._args = args

    @property
    def kwargs(self):
        return self._kwargs

    def get_callee_scope(self, current_scope) -> Scope:
        from .irhelper import qualified_symbols
        qsyms = qualified_symbols(self.func, current_scope)
        symbol = qsyms[-1]
        assert isinstance(symbol, Symbol)
        func_t = symbol.typ
        assert func_t.has_scope()
        return cast(ScopeType, func_t).scope

    def kids(self):
        kids = []
        kids += self._func.kids()
        for _, arg in self._args:
            kids += arg.kids()
        return kids

    def replace(self, old, new):
        if self._func == old:
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

    def find_vars(self, qname: tuple[str, ...]):
        assert len(qname) > 0 and isinstance(qname[0], str)
        vars = self._func.find_vars(qname)
        vars.extend(find_vars_args(self._args, qname))
        vars.extend(find_vars_args(self._kwargs.values(), qname))
        return vars

    def find_irs(self, typ):
        irs = self._func.find_irs(typ)
        irs.extend(find_irs_args(self._args, typ))
        irs.extend(find_irs_args(self._kwargs.values(), typ))
        return irs


class CALL(IRCallable):
    def __init__(self, func:IRVariable, args:list[tuple[str, IRExp]], kwargs:dict[str, IRExp]):
        super().__init__(func, args, kwargs)

    def __str__(self):
        s = f'{self._func}('
        s += ', '.join([str(arg) for name, arg in self._args])
        if self._kwargs:
            s += ', '
            s += ', '.join([f'{name}={value}' for name, value in self._kwargs.items()])
        s += ")"
        return s

    def clone(self):
        func = self._func.clone()
        args = [(name, arg.clone()) for name, arg in self._args]
        kwargs = {name:arg.clone() for name, arg in self._kwargs.items()}
        clone = CALL(func, args, kwargs)
        return clone


class SYSCALL(IRCallable):
    def __init__(self, func:IRVariable, args:list[tuple[str, IRExp]], kwargs:dict[str, IRExp]):
        super().__init__(func, args, kwargs)

    def __str__(self):
        s = f'!{self._func}('
        s += ', '.join([str(arg) for name, arg in self._args])
        if self._kwargs:
            s += ', '
            s += ', '.join([f'{name}={value}' for name, value in self._kwargs.items()])
        s += ")"
        return s

    def clone(self):
        func = self._func.clone()
        args = [(name, arg.clone()) for name, arg in self._args]
        kwargs = {name:arg.clone() for name, arg in self._kwargs.items()}
        clone = SYSCALL(func, args, kwargs)
        return clone


class NEW(IRCallable):
    def __init__(self, func:IRVariable, args:list[tuple[str, IRExp]], kwargs:dict[str, IRExp]):
        super().__init__(func, args, kwargs)

    def __str__(self):
        s = f'${self._func}('
        s += ', '.join([str(arg) for name, arg in self._args])
        if self._kwargs:
            s += ', '
            s += ', '.join([f'{name}={value}' for name, value in self._kwargs.items()])
        s += ")"
        return s

    def clone(self):
        func = self._func.clone()
        args = [(name, arg.clone()) for name, arg in self._args]
        kwargs = {name:arg.clone() for name, arg in self._kwargs.items()}
        clone = NEW(func, args, kwargs)
        return clone


class CONST(IRExp):
    def __init__(self, value, format=None):
        super().__init__()
        self._value = value
        self._format = format

    def __str__(self):
        if isinstance(self._value, bool):
            return str(self._value)
        elif isinstance(self._value, int):
            if self._format == 'hex':
                return hex(self._value)
            elif self._format == 'bin':
                return bin(self._value)
            return str(self._value)
        else:
            return repr(self._value)

    def type_str(self, scope: Scope):
        return type(self._value).__name__

    def __eq__(self, other):
        if other is None or not isinstance(other, CONST):
            return False
        return self._value == other._value

    def __hash__(self):
        return super().__hash__()

    def kids(self):
        return (self,)

    @property
    def value(self):
        return self._value


class MREF(IRExp):
    def __init__(self, mem:IRExp, offset:IRExp, ctx=Ctx.LOAD):
        super().__init__()
        assert mem.is_a([TEMP, ATTR, MREF])
        self._mem = mem
        self._offset = offset
        self._ctx = ctx

    def __str__(self):
        return f'{self._mem}[{self._offset}]'

    def type_str(self, scope: Scope):
        return f'{self._mem.type_str(scope)}[{self._offset.type_str(scope)}]'

    def __eq__(self, other):
        if other is None or not isinstance(other, MREF):
            return False
        return (self._mem == other._mem and self._offset == other._offset and self.ctx == other.ctx)

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
        return f'mstore({self._mem}[{self._offset}], {self._exp})'

    def type_str(self, scope: Scope):
        return f'mstore({self._mem.type_str(scope)}[{self._offset.type_str(scope)}], {self._exp.type_str(scope)})'

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
    def __init__(self, items, mutable: bool):
        super().__init__()
        self._items = items
        self._repeat = CONST(1)
        self._mutable = mutable

    def __str__(self):
        s = '[' if self.is_mutable else '('
        if len(self._items) > 8:
            s += ', '.join(map(str, self._items[:10]))
            s += '...'
        else:
            s += ', '.join(map(str, self._items))
        s += ']' if self.is_mutable else ')'
        if not (self._repeat.is_a(CONST) and self._repeat.value == 1):
            s += ' * ' + str(self._repeat)
        return s

    def type_str(self, scope: Scope):
        from .irhelper import irexp_type
        typ = irexp_type(self, scope)
        s = f'{typ}('
        s += '[' if self.is_mutable else '('
        if len(self._items) > 8:
            s += ', '.join(map(lambda item: item.type_str(scope), self._items[:10]))
            s += '...'
        else:
            s += ', '.join(map(lambda item: item.type_str(scope), self._items))
        s += ']' if self.is_mutable else ')'
        if not (self._repeat.is_a(CONST) and self._repeat.value == 1):
            s += ' * ' + type(self._repeat).__name__
        s += ')'
        return s

    def __eq__(self, other):
        if other is None or not isinstance(other, ARRAY):
            return False
        return (len(self._items) == len(other._items) and
                all([item == other_item for item, other_item in zip(self._items, other._items)]) and
                self._mutable == other._mutable and
                self._repeat == other._repeat)

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
        return self._mutable


class IRVariable(IRNameExp):
    def __init__(self, name: str, ctx: Ctx):
        assert isinstance(name, str)
        assert isinstance(ctx, int)
        super().__init__(name)
        self._ctx = ctx

    def kids(self) -> tuple[IRExp]:
        return (self,)

    @property
    def ctx(self):
        return self._ctx

    @ctx.setter
    def ctx(self, ctx):
        self._ctx = ctx


class TEMP(IRVariable):
    def __init__(self, name: str, ctx=Ctx.LOAD):
        super().__init__(name, ctx)

    def __str__(self):
        return self.name

    def type_str(self, scope: Scope):
        sym = scope.find_sym(self.name)
        if sym:
            return str(sym.typ)
        else:
            return 'unknown'

    def __eq__(self, other):
        if other is None or not isinstance(other, TEMP):
            return False
        return (self.name == other.name and self.ctx == other.ctx)

    def __hash__(self):
        return super().__hash__()


class ATTR(IRVariable):
    def __init__(self, exp: IRVariable, attr: str, ctx=Ctx.LOAD):
        super().__init__(attr.name if isinstance(attr, Symbol) else attr, ctx)
        self._exp = exp
        self._attr = attr
        self._exp.ctx = Ctx.LOAD

    def __str__(self):
        return '{}.{}'.format(self.exp, self._attr)

    def type_str(self, scope: Scope):
        from .irhelper import qualified_symbols
        qsyms = qualified_symbols(self, scope)
        typs = [str(qsym.typ) if isinstance(qsym, Symbol) else 'unknown' for qsym in qsyms]
        return '.'.join(typs)
        # if isinstance(self._attr, str):
        #     return '{}.str'.format(self.exp.type_str())
        # return '{}.{}'.format(self.exp.type_str(), self._attr.typ)

    def __eq__(self, other):
        if other is None or not isinstance(other, ATTR):
            return False
        return (self._exp == other._exp and
                self.name == other.name and
                self.ctx == other.ctx)

    def __hash__(self):
        return super().__hash__()

    # a.b.c.d = (((a.b).c).d)
    #              |    |
    #             head  |
    #                  tail
    def head_name(self) -> str:
        if self._exp.is_a(ATTR):
            return self._exp.head_name()
        elif self._exp.is_a(TEMP):
            return self._exp.name
        else:
            return ''

    def tail_name(self):
        return self._exp.name

    @property
    def qualified_name(self) -> tuple[str, ...]:
        return self._exp.qualified_name + (self.name,)

    def replace_head(self, new_head_name: str):
        if self._exp.is_a(ATTR):
            self._exp.replace_head(new_head_name)
        else:
            self._exp.name = new_head_name
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
        self.block:'Block' = None

    def program_order(self):
        return (self.block.order, find_id_index(self.block.stms, self))

    def kids(self) -> tuple[IRExp]:
        return tuple()

    def is_mem_read(self):
        return self.is_a(MOVE) and self.src.is_a(MREF)

    def is_mem_write(self):
        return self.is_a(EXPR) and self.exp.is_a(MSTORE)


class EXPR(IRStm):
    def __init__(self, exp, loc=None):
        super().__init__(loc)
        self._exp = exp

    def __str__(self):
        return str(self._exp)

    def type_str(self, scope: Scope):
        return str(self._exp.type_str(scope))

    def __eq__(self, other):
        if other is None or not isinstance(other, EXPR):
            return False
        return self._exp == other._exp

    def __hash__(self):
        return super().__hash__()

    def kids(self) -> tuple[IRExp]:
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

    def type_str(self, scope: Scope):
        return ''

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
    def __init__(self, conds, targets, loc=None):
        super().__init__(loc)
        self._conds = conds
        self._targets = targets
        self._loop_branch = False

    def __str__(self):
        assert len(self._conds) == len(self._targets)
        items = []
        for cond, target in zip(self._conds, self._targets):
            items.append('{} ? {}'.format(cond, target.name))

        return 'mcjump(\n        {})'.format(', \n        '.join([item for item in items]))

    def type_str(self, scope: Scope):
        return ''

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

    def type_str(self, scope: Scope):
        return ''

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
    def __init__(self, exp:IRExp|str|int, loc=None):
        super().__init__(loc)
        if isinstance(exp, str):
            self._exp = name2var(exp, ctx=Ctx.LOAD)
        elif isinstance(exp, int):
            self._exp = CONST(exp)
        else:
            self._exp = exp

    def __str__(self):
        return f"return {self._exp}"

    def type_str(self, scope: Scope):
        return str(self._exp.type_str(scope))

    def __eq__(self, other):
        if other is None or not isinstance(other, RET):
            return False
        return self._exp == other._exp

    def __hash__(self):
        return super().__hash__()

    def kids(self) -> tuple[IRExp]:
        return self._exp.kids()

    @property
    def exp(self):
        return self._exp

    @exp.setter
    def exp(self, e):
        self._exp = e


class MOVE(IRStm):
    def __init__(self, dst:IRExp|str, src:IRExp|str|int, loc=None):
        super().__init__(loc)
        if isinstance(dst, str):
            self._dst = name2var(dst, ctx=Ctx.STORE)
        elif isinstance(dst, IRVariable):
            dst.ctx = Ctx.STORE
            self._dst = dst
        else:
            self._dst = dst
        if isinstance(src, str):
            self._src = name2var(src, ctx=Ctx.LOAD)
        elif isinstance(src, int):
            self._src = CONST(src)
        elif isinstance(src, IRVariable):
            src.ctx = Ctx.LOAD
            self._src = src
        else:
            self._src = src

    def __str__(self):
        return f'{self._dst} = {self._src}'

    def type_str(self, scope: Scope):
        return f'{self._dst.type_str(scope)} = {self._src.type_str(scope)}'

    def __eq__(self, other):
        if other is None or not isinstance(other, MOVE):
            return False
        return self._dst == other._dst and self._src == other._src

    def __hash__(self):
        return super().__hash__()

    def kids(self) -> tuple[IRExp]:
        return self._dst.kids() + self._src.kids()

    @property
    def src(self) -> IRExp:
        return self._src

    @src.setter
    def src(self, src):
        self._src = src

    @property
    def dst(self) -> IRVariable:
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
        return f"{self._cond} ? {super().__str__()}"

    def type_str(self, scope: Scope):
        return f"{self._cond.type_str(scope)} ? {super().type_str(scope)}"

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
        return f"{self._cond} ? {super().__str__()}"

    def type_str(self, scope: Scope):
        return f"{self._cond.type_str(scope)} ? {super().type_str(scope)}"

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
    def __init__(self, var: IRVariable):
        super().__init__(loc=None)
        assert isinstance(var, IRVariable)
        self._var = var
        self._var.ctx = Ctx.STORE
        self._args: list[IRVariable] = []
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

    def type_str(self, scope: Scope):
        return ''

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
        return self._var.kids() + tuple(kids)

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

    def type_str(self, scope: Scope):
        return ''

    def __eq__(self, other):
        if other is None or not isinstance(other, MSTM):
            return False
        return all([a == b for a, b in zip(self._stms, other._stms)])

    def __hash__(self):
        return super().__hash__()

    @property
    def stms(self):
        return self._stms


def name2var(name: str, ctx: Ctx=Ctx.LOAD) -> IRVariable:
    ss = name.split('.')
    exp = TEMP(ss[0])
    for s in ss[1:]:
        exp = ATTR(exp, s)
    exp.ctx = ctx
    return exp


def move(src, dst):
    if isinstance(src, str):
        src = name2var(src, ctx=Ctx.LOAD)
    elif isinstance(src, int):
        src = CONST(src)
    if isinstance(dst, str):
        dst = name2var(dst, ctx=Ctx.STORE)
    return MOVE(dst, src)
