"""Pydantic-based IR model classes.

New IR classes using pydantic BaseModel. These coexist with the old IR
classes in ir.py during the migration period. Conversion functions in
ir_converter.py bridge between the two representations.
"""
from __future__ import annotations
from typing import Any
from collections import namedtuple
from enum import IntEnum
from pydantic import BaseModel, ConfigDict, field_validator


op2sym_map = {
    'And': 'and', 'Or': 'or',
    'Add': '+', 'Sub': '-', 'Mult': '*', 'FloorDiv': '//', 'Mod': '%',
    'LShift': '<<', 'RShift': '>>',
    'BitOr': '|', 'BitXor': '^', 'BitAnd': '&',
    'Eq': '==', 'NotEq': '!=', 'Lt': '<', 'LtE': '<=', 'Gt': '>', 'GtE': '>=',
    'IsNot': '!=',
    'USub': '-', 'UAdd': '+', 'Not': '!', 'Invert': '~',
}

BINOP_OPS = {'Add', 'Sub', 'Mult', 'FloorDiv', 'Mod',
             'LShift', 'RShift', 'BitOr', 'BitXor', 'BitAnd'}
RELOP_OPS = {'And', 'Or', 'Eq', 'NotEq', 'Lt', 'LtE', 'Gt', 'GtE', 'IsNot'}
UNOP_OPS = {'USub', 'UAdd', 'Not', 'Invert'}


class Ctx(IntEnum):
    LOAD = 1
    STORE = 2
    CALL = 3


Loc = namedtuple('Loc', ('filename', 'lineno'))


# ============================================================
# Base classes
# ============================================================

class Ir(BaseModel):
    model_config = ConfigDict(frozen=False, arbitrary_types_allowed=True)

    def __repr__(self):
        return self.__str__()

    def __hash__(self):
        return id(self)

    def __lt__(self, other):
        return id(self) < id(other)


class IrExp(Ir):
    pass


class IrStm(Ir):
    loc: Any = None
    block: Any = None  # Block reference


# ============================================================
# IrExp — Name / Variable
# ============================================================

class IrNameExp(IrExp):
    name: str

    @property
    def qualified_name(self) -> tuple[str, ...]:
        return (self.name,)


class IrVariable(IrNameExp):
    ctx: Ctx

    def kids(self) -> tuple:
        return (self,)


class Temp(IrVariable):
    ctx: Ctx = Ctx.LOAD

    def __str__(self):
        return self.name

    def __eq__(self, other):
        if not isinstance(other, Temp):
            return False
        return self.name == other.name and self.ctx == other.ctx

    def __hash__(self):
        return id(self)


class Attr(IrVariable):
    exp: IrVariable
    attr: Any  # str or Symbol
    ctx: Ctx = Ctx.LOAD

    def model_post_init(self, __context):
        if not self.name:
            if isinstance(self.attr, str):
                self.name = self.attr
            else:
                self.name = self.attr.name

    def __str__(self):
        return f'{self.exp}.{self.attr}'

    def __eq__(self, other):
        if not isinstance(other, Attr):
            return False
        return self.exp == other.exp and self.name == other.name and self.ctx == other.ctx

    def __hash__(self):
        return id(self)

    @property
    def qualified_name(self) -> tuple[str, ...]:
        return self.exp.qualified_name + (self.name,)

    def head_name(self) -> str:
        if isinstance(self.exp, Attr):
            return self.exp.head_name()
        elif isinstance(self.exp, Temp):
            return self.exp.name
        return ''

    def tail_name(self) -> str:
        return self.exp.name


# ============================================================
# IrExp — Constants
# ============================================================

class Const(IrExp):
    value: Any = None
    format: str | None = None

    def __str__(self):
        if isinstance(self.value, bool):
            return str(self.value)
        elif isinstance(self.value, int):
            if self.format == 'hex':
                return hex(self.value)
            elif self.format == 'bin':
                return bin(self.value)
            return str(self.value)
        else:
            return repr(self.value)

    def __eq__(self, other):
        if not isinstance(other, Const):
            return False
        return self.value == other.value

    def __hash__(self):
        return id(self)

    def kids(self):
        return (self,)


# ============================================================
# IrExp — Operators
# ============================================================

class UnOp(IrExp):
    op: str
    exp: IrExp

    @field_validator('op')
    @classmethod
    def validate_op(cls, v):
        if v not in UNOP_OPS:
            raise ValueError(f'Invalid UnOp op: {v}')
        return v

    def __str__(self):
        return f'{op2sym_map[self.op]}{self.exp}'

    def __eq__(self, other):
        if not isinstance(other, UnOp):
            return False
        return self.op == other.op and self.exp == other.exp

    def __hash__(self):
        return id(self)

    def kids(self):
        return self.exp.kids()


class BinOp(IrExp):
    op: str
    left: IrExp
    right: IrExp

    @field_validator('op')
    @classmethod
    def validate_op(cls, v):
        if v not in BINOP_OPS:
            raise ValueError(f'Invalid BinOp op: {v}')
        return v

    def __str__(self):
        return f'({self.left} {op2sym_map[self.op]} {self.right})'

    def __eq__(self, other):
        if not isinstance(other, BinOp):
            return False
        return self.op == other.op and self.left == other.left and self.right == other.right

    def __hash__(self):
        return id(self)

    def kids(self):
        return self.left.kids() + self.right.kids()


class RelOp(IrExp):
    op: str
    left: IrExp
    right: IrExp

    @field_validator('op')
    @classmethod
    def validate_op(cls, v):
        if v not in RELOP_OPS:
            raise ValueError(f'Invalid RelOp op: {v}')
        return v

    def __str__(self):
        return f'({self.left} {op2sym_map[self.op]} {self.right})'

    def __eq__(self, other):
        if not isinstance(other, RelOp):
            return False
        return self.op == other.op and self.left == other.left and self.right == other.right

    def __hash__(self):
        return id(self)

    def kids(self):
        return self.left.kids() + self.right.kids()


class CondOp(IrExp):
    cond: IrExp
    left: IrExp
    right: IrExp

    def __str__(self):
        return f'({self.cond} ? {self.left} : {self.right})'

    def __eq__(self, other):
        if not isinstance(other, CondOp):
            return False
        return self.cond == other.cond and self.left == other.left and self.right == other.right

    def __hash__(self):
        return id(self)

    def kids(self):
        return self.cond.kids() + self.left.kids() + self.right.kids()


class PolyOp(IrExp):
    op: str
    values: list[IrExp]

    def __str__(self):
        values = ', '.join([str(e) for e in self.values])
        return f'({op2sym_map[self.op]} [{values}])'

    def __hash__(self):
        return id(self)

    def kids(self):
        return self.values


# ============================================================
# IrExp — Callable (Call, SysCall, New)
# ============================================================

class IrCallable(IrNameExp):
    func: IrVariable
    args: list = []
    kwargs: dict = {}

    @property
    def name(self) -> str:
        return self.func.name

    @name.setter
    def name(self, name):
        self.func.name = name

    @property
    def qualified_name(self) -> tuple[str, ...]:
        return self.func.qualified_name

    def __eq__(self, other):
        if not isinstance(other, IrCallable):
            return False
        return (self.func == other.func and
                len(self.args) == len(other.args) and
                all(n == on and a == oa for (n, a), (on, oa) in zip(self.args, other.args)))

    def __hash__(self):
        return id(self)

    def kids(self):
        kids = list(self.func.kids())
        for _, arg in self.args:
            kids += list(arg.kids())
        return tuple(kids)


class Call(IrCallable):
    def __str__(self):
        s = f'{self.func}('
        s += ', '.join([str(arg) for _, arg in self.args])
        if self.kwargs:
            s += ', '
            s += ', '.join([f'{name}={value}' for name, value in self.kwargs.items()])
        s += ')'
        return s


class SysCall(IrCallable):
    def __str__(self):
        s = f'!{self.func}('
        s += ', '.join([str(arg) for _, arg in self.args])
        if self.kwargs:
            s += ', '
            s += ', '.join([f'{name}={value}' for name, value in self.kwargs.items()])
        s += ')'
        return s


class New(IrCallable):
    def __str__(self):
        s = f'${self.func}('
        s += ', '.join([str(arg) for _, arg in self.args])
        if self.kwargs:
            s += ', '
            s += ', '.join([f'{name}={value}' for name, value in self.kwargs.items()])
        s += ')'
        return s


# ============================================================
# IrExp — Memory operations
# ============================================================

class MRef(IrExp):
    mem: IrExp
    offset: IrExp
    ctx: Ctx = Ctx.LOAD

    def __str__(self):
        return f'{self.mem}[{self.offset}]'

    def __eq__(self, other):
        if not isinstance(other, MRef):
            return False
        return self.mem == other.mem and self.offset == other.offset and self.ctx == other.ctx

    def __hash__(self):
        return id(self)

    def kids(self):
        return self.mem.kids() + self.offset.kids()


class MStore(IrExp):
    mem: IrExp
    offset: IrExp
    exp: IrExp

    def __str__(self):
        return f'mstore({self.mem}[{self.offset}], {self.exp})'

    def __eq__(self, other):
        if not isinstance(other, MStore):
            return False
        return self.mem == other.mem and self.offset == other.offset and self.exp == other.exp

    def __hash__(self):
        return id(self)

    def kids(self):
        return self.mem.kids() + self.offset.kids() + self.exp.kids()


# ============================================================
# IrExp — Array
# ============================================================

class Array(IrExp):
    items: list = []
    repeat: Any = None  # Const(1) default, set in post_init
    mutable: bool = True

    def model_post_init(self, __context):
        if self.repeat is None:
            self.repeat = Const(value=1)

    @property
    def is_mutable(self):
        return self.mutable

    def __str__(self):
        s = '[' if self.mutable else '('
        if len(self.items) > 8:
            s += ', '.join(map(str, self.items[:10]))
            s += '...'
        else:
            s += ', '.join(map(str, self.items))
        s += ']' if self.mutable else ')'
        if not (isinstance(self.repeat, Const) and self.repeat.value == 1):
            s += ' * ' + str(self.repeat)
        return s

    def __eq__(self, other):
        if not isinstance(other, Array):
            return False
        return (len(self.items) == len(other.items) and
                all(a == b for a, b in zip(self.items, other.items)) and
                self.mutable == other.mutable and
                self.repeat == other.repeat)

    def __hash__(self):
        return id(self)

    def getlen(self):
        if isinstance(self.repeat, Const):
            return len(self.items) * self.repeat.value
        return -1

    def kids(self):
        kids = []
        for item in self.items:
            kids += list(item.kids())
        return tuple(kids)


# ============================================================
# IrStm — Statements
# ============================================================

class Expr(IrStm):
    exp: IrExp

    def __str__(self):
        return str(self.exp)

    def __eq__(self, other):
        if not isinstance(other, Expr):
            return False
        return self.exp == other.exp

    def __hash__(self):
        return id(self)

    def kids(self):
        return self.exp.kids()


class CExpr(Expr):
    cond: IrExp

    def __str__(self):
        return f'{self.cond} ? {self.exp}'

    def __eq__(self, other):
        if not isinstance(other, CExpr):
            return False
        return self.cond == other.cond and self.exp == other.exp

    def __hash__(self):
        return id(self)

    def kids(self):
        return self.cond.kids() + self.exp.kids()


class Move(IrStm):
    dst: IrExp
    src: IrExp

    def __str__(self):
        return f'{self.dst} = {self.src}'

    def __eq__(self, other):
        if not isinstance(other, Move):
            return False
        return self.dst == other.dst and self.src == other.src

    def __hash__(self):
        return id(self)

    def kids(self):
        return self.dst.kids() + self.src.kids()


class CMove(Move):
    cond: IrExp

    def __str__(self):
        return f'{self.cond} ? {self.dst} = {self.src}'

    def __eq__(self, other):
        if not isinstance(other, CMove):
            return False
        return self.cond == other.cond and self.dst == other.dst and self.src == other.src

    def __hash__(self):
        return id(self)

    def kids(self):
        return self.cond.kids() + self.dst.kids() + self.src.kids()


class Jump(IrStm):
    target: Any  # Block
    typ: str = ''

    def __str__(self):
        return f"jump {self.target.name} '{self.typ}'"

    def __eq__(self, other):
        if not isinstance(other, Jump):
            return False
        return self.target is other.target

    def __hash__(self):
        return id(self)


class CJump(IrStm):
    exp: IrExp
    true: Any  # Block
    false: Any  # Block
    loop_branch: bool = False

    def __str__(self):
        return f'cjump {self.exp} ? {self.true.name}, {self.false.name}'

    def __eq__(self, other):
        if not isinstance(other, CJump):
            return False
        return self.exp == other.exp and self.true is other.true and self.false is other.false

    def __hash__(self):
        return id(self)


class MCJump(IrStm):
    conds: list = []
    targets: list = []
    loop_branch: bool = False

    def __str__(self):
        items = []
        for cond, target in zip(self.conds, self.targets):
            items.append(f'{cond} ? {target.name}')
        return 'mcjump(\n        {})'.format(', \n        '.join(items))

    def __eq__(self, other):
        if not isinstance(other, MCJump):
            return False
        return (len(self.conds) == len(other.conds) and
                all(c == oc for c, oc in zip(self.conds, other.conds)) and
                all(t is ot for t, ot in zip(self.targets, other.targets)))

    def __hash__(self):
        return id(self)


class Ret(IrStm):
    exp: IrExp

    def __str__(self):
        return f'return {self.exp}'

    def __eq__(self, other):
        if not isinstance(other, Ret):
            return False
        return self.exp == other.exp

    def __hash__(self):
        return id(self)

    def kids(self):
        return self.exp.kids()


class Phi(IrStm):
    var: IrVariable
    args: list = []
    ps: list = []

    def __str__(self):
        delim = ',\n        ' if len(self.args) >= 2 else ', '
        str_args = []
        if self.ps:
            for arg, p in zip(self.args, self.ps):
                str_args.append(f'{p} ? {arg}' if arg else '_')
        else:
            for arg in self.args:
                str_args.append(str(arg) if arg else '_')
        return f'{self.var} = phi({delim.join(str_args)})'

    def __eq__(self, other):
        if not isinstance(other, Phi):
            return False
        return self.var == other.var

    def __hash__(self):
        return id(self)

    def kids(self):
        kids = list(self.var.kids())
        for arg in self.args:
            if arg:
                kids += list(arg.kids())
        return tuple(kids)


class UPhi(Phi):
    def __str__(self):
        str_args = []
        for arg in self.args:
            str_args.append(str(arg) if arg else '_')
        return f'{self.var} = uphi({", ".join(str_args)})'


class LPhi(Phi):
    def __str__(self):
        str_args = []
        for arg in self.args:
            str_args.append(str(arg) if arg else '_')
        return f'{self.var} = lphi({", ".join(str_args)})'


class MStm(IrStm):
    stms: list = []

    def __str__(self):
        return 'mstm{{{}}}'.format(', '.join([str(stm) for stm in self.stms]))

    def __eq__(self, other):
        if not isinstance(other, MStm):
            return False
        return all(a == b for a, b in zip(self.stms, other.stms))

    def __hash__(self):
        return id(self)
