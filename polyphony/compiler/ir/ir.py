"""Pydantic-based IR model classes.

Unified IR using pydantic BaseModel. Old and new IR are now the same.
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
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    def __repr__(self):
        return self.__str__()

    def __hash__(self):
        return id(self)

    def __lt__(self, other):
        return id(self) < id(other)

    def type_str(self, scope):
        """Return a type-annotated string representation (for debug logging)."""
        return ''

    def clone(self, **overrides):
        """Deep-copy this IR node, returning a new instance via __init__."""
        data = {}
        for field_name in type(self).model_fields:
            v = getattr(self, field_name, None)
            if isinstance(v, Ir):
                data[field_name] = v.clone()
            elif isinstance(v, list):
                assert False, f'{type(self).__name__}.{field_name} must not be a list'
            elif isinstance(v, tuple) and not hasattr(v, '_fields'):
                new_seq = []
                for elm in v:
                    if isinstance(elm, Ir):
                        new_seq.append(elm.clone())
                    elif isinstance(elm, tuple):
                        new_tuple = tuple(
                            e.clone() if isinstance(e, Ir) else e for e in elm
                        )
                        new_seq.append(new_tuple)
                    else:
                        new_seq.append(elm)
                data[field_name] = type(v)(new_seq)
            elif isinstance(v, dict):
                new_dict = {}
                for k, dv in v.items():
                    if isinstance(dv, Ir):
                        new_dict[k] = dv.clone()
                    else:
                        new_dict[k] = dv
                data[field_name] = new_dict
            else:
                data[field_name] = v
        data.update(overrides)
        return self.__class__(**data)

    def subst(self, old, new):
        """Return a new IR tree with all occurrences of old replaced by new.

        Non-mutating: self is unchanged. Returns the same object if nothing was replaced.
        """
        result, _ = self._subst_rec(self, old, new, set())
        return result

    def _subst_rec(self, ir, old, new, visited):
        """Return (new_ir, changed). Non-mutating replacement."""
        if isinstance(ir, Ir):
            obj_id = id(ir)
            if obj_id in visited:
                return ir, False
            visited.add(obj_id)
            updates = {}
            for field_name in type(ir).model_fields:
                v = getattr(ir, field_name, None)
                if v == old:
                    updates[field_name] = new
                elif isinstance(v, list):
                    assert False, f'{type(ir).__name__}.{field_name} must not be a list'
                elif isinstance(v, tuple):
                    new_v, changed = self._subst_seq(v, old, new, visited)
                    if changed:
                        updates[field_name] = new_v
                else:
                    new_v, changed = self._subst_rec(v, old, new, visited)
                    if changed:
                        updates[field_name] = new_v
            if updates:
                return ir.model_copy(update=updates), True
            return ir, False
        elif isinstance(ir, list):
            assert False, 'IR sequence must not be a list'
        elif isinstance(ir, tuple):
            return self._subst_seq(ir, old, new, visited)
        return ir, False

    def _subst_seq(self, seq, old, new, visited):
        """Return (new_seq, changed) for a tuple."""
        new_elms = list(seq)
        changed = False
        for i, elm in enumerate(seq):
            if elm == old:
                new_elms[i] = new
                changed = True
            else:
                new_elm, elm_changed = self._subst_rec(elm, old, new, visited)
                if elm_changed:
                    new_elms[i] = new_elm
                    changed = True
        if not changed:
            return seq, False
        return tuple(new_elms), True

    def find_vars(self, qname):
        """Find all variables matching the given qualified name."""
        assert len(qname) > 0 and isinstance(qname[0], str)
        vars = []
        self._find_vars_rec(self, qname, vars)
        return vars

    def _find_vars_rec(self, ir, qname, vars, visited=None):
        if visited is None:
            visited = set()
        obj_id = id(ir)
        if obj_id in visited:
            return
        visited.add(obj_id)
        if isinstance(ir, Ir):
            if isinstance(ir, Temp):
                if ir.qualified_name == qname:
                    vars.append(ir)
            elif isinstance(ir, Attr):
                if ir.qualified_name == qname:
                    vars.append(ir)
                else:
                    self._find_vars_rec(ir.exp, qname, vars, visited)
            else:
                for field_name in type(ir).model_fields:
                    v = getattr(ir, field_name, None)
                    self._find_vars_rec(v, qname, vars, visited)
        elif isinstance(ir, list):
            assert False, 'IR sequence must not be a list'
        elif isinstance(ir, tuple):
            for elm in ir:
                self._find_vars_rec(elm, qname, vars, visited)

    def find_irs(self, typ):
        """Find all descendant nodes matching the given type."""
        irs = []
        self._find_irs_rec(self, typ, irs)
        return irs

    def _find_irs_rec(self, ir, typ, irs, visited=None):
        if visited is None:
            visited = set()
        obj_id = id(ir)
        if obj_id in visited:
            return
        visited.add(obj_id)
        if isinstance(ir, Ir):
            if isinstance(ir, typ):
                irs.append(ir)
            for field_name in type(ir).model_fields:
                v = getattr(ir, field_name, None)
                self._find_irs_rec(v, typ, irs, visited)
        elif isinstance(ir, list):
            assert False, 'IR sequence must not be a list'
        elif isinstance(ir, tuple):
            for elm in ir:
                self._find_irs_rec(elm, typ, irs, visited)


class IrExp(Ir):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)


class IrStm(Ir):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    loc: Any = None
    block: str = ''  # block bid (e.g., 'b1', 'loop3')

    @field_validator('block', mode='before')
    @classmethod
    def _coerce_block(cls, v):
        if isinstance(v, str):
            return v
        # Accept Block objects for backward compat - extract bid
        if hasattr(v, 'bid'):
            return v.bid
        return str(v)

    def model_post_init(self, __context):
        """Ensure loc is never None."""
        if self.loc is None:
            object.__setattr__(self, 'loc', Loc('', 0))

    def is_mem_read(self):
        return isinstance(self, Move) and isinstance(self.src, MRef)

    def is_mem_write(self):
        return isinstance(self, Expr) and isinstance(self.exp, MStore)


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

    def __init__(self, *args, **kwargs):
        """Accept positional args: Temp(name, ctx=Ctx.LOAD)"""
        if args:
            if len(args) >= 1:
                kwargs.setdefault('name', args[0])
            if len(args) >= 2:
                kwargs.setdefault('ctx', args[1])
        super().__init__(**kwargs)

    def __str__(self):
        return self.name

    def __eq__(self, other):
        if not isinstance(other, Temp):
            return False
        return self.name == other.name and self.ctx == other.ctx

    def __hash__(self):
        return id(self)


class Attr(IrVariable):
    exp: IrExp  # Usually IrVariable, but can be Call/New/etc. (e.g., $D().method)
    attr: Any  # str or Symbol
    ctx: Ctx = Ctx.LOAD

    def __init__(self, *args, **kwargs):
        """Accept positional args: Attr(exp, attr, ctx=Ctx.LOAD)"""
        if args:
            if len(args) >= 1:
                kwargs.setdefault('exp', args[0])
            if len(args) >= 2:
                kwargs.setdefault('attr', args[1])
            if len(args) >= 3:
                kwargs.setdefault('ctx', args[2])
        # Derive name from attr if not provided (matches old ATTR behavior)
        attr = kwargs.get('attr')
        if 'name' not in kwargs and attr is not None:
            from .symbol import Symbol
            if isinstance(attr, Symbol):
                kwargs['name'] = attr.name
            elif isinstance(attr, str):
                kwargs['name'] = attr
            else:
                kwargs['name'] = ''
        # Set exp.ctx = LOAD to match old ATTR behavior
        exp = kwargs.get('exp')
        if exp is not None and hasattr(exp, 'ctx') and exp.ctx != Ctx.LOAD:
            kwargs['exp'] = exp.model_copy(update={'ctx': Ctx.LOAD})
        super().__init__(**kwargs)

    def model_post_init(self, __context):
        if not self.name:
            if isinstance(self.attr, str):
                object.__setattr__(self, 'name', self.attr)
            else:
                object.__setattr__(self, 'name', self.attr.name)

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

    def __init__(self, *args, **kwargs):
        """Accept positional args: Const(value, format=None)"""
        if args:
            if len(args) >= 1:
                kwargs.setdefault('value', args[0])
            if len(args) >= 2:
                kwargs.setdefault('format', args[1])
        super().__init__(**kwargs)

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

    def __init__(self, *args, **kwargs):
        """Accept positional args: UnOp(op, exp)"""
        if args:
            if len(args) >= 1:
                kwargs.setdefault('op', args[0])
            if len(args) >= 2:
                kwargs.setdefault('exp', args[1])
        super().__init__(**kwargs)

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

    def __init__(self, *args, **kwargs):
        """Accept positional args: BinOp(op, left, right)"""
        if args:
            if len(args) >= 1:
                kwargs.setdefault('op', args[0])
            if len(args) >= 2:
                kwargs.setdefault('left', args[1])
            if len(args) >= 3:
                kwargs.setdefault('right', args[2])
        super().__init__(**kwargs)

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

    def __init__(self, *args, **kwargs):
        """Accept positional args: RelOp(op, left, right)"""
        if args:
            if len(args) >= 1:
                kwargs.setdefault('op', args[0])
            if len(args) >= 2:
                kwargs.setdefault('left', args[1])
            if len(args) >= 3:
                kwargs.setdefault('right', args[2])
        super().__init__(**kwargs)

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

    def __init__(self, *args, **kwargs):
        """Accept positional args: CondOp(cond, left, right)"""
        if args:
            if len(args) >= 1:
                kwargs.setdefault('cond', args[0])
            if len(args) >= 2:
                kwargs.setdefault('left', args[1])
            if len(args) >= 3:
                kwargs.setdefault('right', args[2])
        super().__init__(**kwargs)

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
    values: tuple[IrExp, ...]

    def __init__(self, *args, **kwargs):
        """Accept positional args: PolyOp(op, values)"""
        if args:
            if len(args) >= 1:
                kwargs.setdefault('op', args[0])
            if len(args) >= 2:
                v = args[1]
                kwargs.setdefault('values', tuple(v) if isinstance(v, list) else v)
        super().__init__(**kwargs)

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
    name: str = ''
    func: IrVariable
    args: tuple = ()
    kwargs: dict = {}

    def __init__(self, *args_pos, **kwargs):
        """Accept positional args: IrCallable(func, args, kwargs)"""
        if args_pos:
            if len(args_pos) >= 1:
                kwargs.setdefault('func', args_pos[0])
            if len(args_pos) >= 2:
                kwargs.setdefault('args', args_pos[1])
            if len(args_pos) >= 3:
                kwargs.setdefault('kwargs', args_pos[2])
        # Ensure args is a tuple
        if 'args' in kwargs and not isinstance(kwargs['args'], tuple):
            kwargs['args'] = tuple(kwargs['args'])
        # Set func.ctx = CALL
        func = kwargs.get('func')
        if func is not None and hasattr(func, 'ctx') and func.ctx != Ctx.CALL:
            kwargs['func'] = func.model_copy(update={'ctx': Ctx.CALL})
        super().__init__(**kwargs)

    def model_post_init(self, __context):
        """Sync the name field from func.name.

        In Pydantic, the inherited 'name' field from IrNameExp is a model field,
        so we sync its value from func.name after construction.
        """
        object.__setattr__(self, 'name', self.func.name)

    # NOTE: No __setattr__ override needed. IrExp is frozen, so direct field
    # assignment raises ValidationError. func.ctx=CALL is ensured in __init__,
    # and name is synced in model_post_init. Mutations use object.__setattr__
    # or model_copy.

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

    def get_callee_scope(self, current_scope):
        """Resolve the scope of the function being called."""
        from .irhelper import qualified_symbols
        from .symbol import Symbol
        from .types.scopetype import ScopeType
        qsyms = qualified_symbols(self.func, current_scope)
        symbol = qsyms[-1]
        assert isinstance(symbol, Symbol)
        func_t = symbol.typ
        assert func_t.has_scope()
        return func_t.scope


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

    def __init__(self, *args, **kwargs):
        """Accept positional args: MRef(mem, offset, ctx=Ctx.LOAD)"""
        if args:
            if len(args) >= 1:
                kwargs.setdefault('mem', args[0])
            if len(args) >= 2:
                kwargs.setdefault('offset', args[1])
            if len(args) >= 3:
                kwargs.setdefault('ctx', args[2])
        super().__init__(**kwargs)

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

    def __init__(self, *args, **kwargs):
        """Accept positional args: MStore(mem, offset, exp)"""
        if args:
            if len(args) >= 1:
                kwargs.setdefault('mem', args[0])
            if len(args) >= 2:
                kwargs.setdefault('offset', args[1])
            if len(args) >= 3:
                kwargs.setdefault('exp', args[2])
        super().__init__(**kwargs)

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
    items: tuple = ()
    repeat: Any = None  # Const(1) default, set in post_init
    mutable: bool = True

    def __init__(self, *args, **kwargs):
        """Accept positional args: Array(items, mutable)"""
        if args:
            if len(args) >= 1:
                kwargs.setdefault('items', args[0])
            if len(args) >= 2:
                kwargs.setdefault('mutable', args[1])
        if 'items' in kwargs and not isinstance(kwargs['items'], tuple):
            kwargs['items'] = tuple(kwargs['items'])
        super().__init__(**kwargs)

    def model_post_init(self, __context):
        if self.repeat is None:
            object.__setattr__(self, 'repeat', Const(value=1))

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

    def __init__(self, *args, **kwargs):
        """Accept positional args: Expr(exp, loc=None)"""
        if args:
            if len(args) >= 1:
                kwargs.setdefault('exp', args[0])
            if len(args) >= 2:
                kwargs.setdefault('loc', args[1])
        super().__init__(**kwargs)

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

    def __init__(self, *args, **kwargs):
        """Accept positional args: CExpr(cond, exp, loc=None)"""
        if args:
            if len(args) >= 1:
                kwargs.setdefault('cond', args[0])
            if len(args) >= 2:
                kwargs.setdefault('exp', args[1])
            if len(args) >= 3:
                kwargs.setdefault('loc', args[2])
        super().__init__(**kwargs)

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

    def __init__(self, *args, **kwargs):
        """Accept positional args: Move(dst, src, loc=None) with str/int coercion."""
        if args:
            if len(args) >= 1:
                kwargs.setdefault('dst', args[0])
            if len(args) >= 2:
                kwargs.setdefault('src', args[1])
            if len(args) >= 3:
                kwargs.setdefault('loc', args[2])
        # Coerce dst: str -> Temp chain, IrVariable -> set ctx to STORE
        dst = kwargs.get('dst')
        if isinstance(dst, str):
            kwargs['dst'] = name2var(dst, ctx=Ctx.STORE)
        elif isinstance(dst, IrVariable) and not isinstance(dst, (MRef,)):
            if dst.ctx != Ctx.STORE:
                kwargs['dst'] = dst.model_copy(update={'ctx': Ctx.STORE})
        # Coerce src: str -> Temp chain, int -> Const, IrVariable -> set ctx to LOAD
        src = kwargs.get('src')
        if isinstance(src, str):
            kwargs['src'] = name2var(src, ctx=Ctx.LOAD)
        elif isinstance(src, int) and not isinstance(src, bool):
            kwargs['src'] = Const(value=src)
        elif isinstance(src, IrVariable):
            if src.ctx != Ctx.LOAD:
                kwargs['src'] = src.model_copy(update={'ctx': Ctx.LOAD})
        super().__init__(**kwargs)

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

    def __init__(self, *args, **kwargs):
        """Accept positional args: CMove(cond, dst, src, loc=None)"""
        if args:
            if len(args) >= 1:
                kwargs.setdefault('cond', args[0])
            if len(args) >= 2:
                kwargs.setdefault('dst', args[1])
            if len(args) >= 3:
                kwargs.setdefault('src', args[2])
            if len(args) >= 4:
                kwargs.setdefault('loc', args[3])
        super().__init__(**kwargs)

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
    target: str  # block bid
    typ: str = ''

    @field_validator('target', mode='before')
    @classmethod
    def _coerce_target(cls, v):
        if isinstance(v, str):
            return v
        if hasattr(v, 'bid'):
            return v.bid
        return str(v) if v is not None else ''

    def __init__(self, *args, **kwargs):
        """Accept positional args: Jump(target, typ='', loc=None)"""
        if args:
            if len(args) >= 1:
                kwargs.setdefault('target', args[0])
            if len(args) >= 2:
                kwargs.setdefault('typ', args[1])
            if len(args) >= 3:
                kwargs.setdefault('loc', args[2])
        super().__init__(**kwargs)

    def __str__(self):
        return f"jump {self.target} '{self.typ}'"

    def __eq__(self, other):
        if not isinstance(other, Jump):
            return False
        return self.target == other.target

    def __hash__(self):
        return id(self)


def _coerce_bid(v):
    if isinstance(v, str):
        return v
    if hasattr(v, 'bid'):
        return v.bid
    return str(v) if v is not None else ''


class CJump(IrStm):
    exp: IrExp
    true: str   # block bid
    false: str  # block bid
    loop_branch: bool = False

    @field_validator('true', 'false', mode='before')
    @classmethod
    def _coerce_targets(cls, v):
        return _coerce_bid(v)

    def __init__(self, *args, **kwargs):
        """Accept positional args: CJump(exp, true, false, loc=None)"""
        if args:
            if len(args) >= 1:
                kwargs.setdefault('exp', args[0])
            if len(args) >= 2:
                kwargs.setdefault('true', args[1])
            if len(args) >= 3:
                kwargs.setdefault('false', args[2])
            if len(args) >= 4:
                kwargs.setdefault('loc', args[3])
        super().__init__(**kwargs)

    def __str__(self):
        return f'cjump {self.exp} ? {self.true}, {self.false}'

    def __eq__(self, other):
        if not isinstance(other, CJump):
            return False
        return self.exp == other.exp and self.true == other.true and self.false == other.false

    def __hash__(self):
        return id(self)


class MCJump(IrStm):
    conds: tuple = ()
    targets: tuple[str, ...] = ()  # block bids
    loop_branch: bool = False

    @field_validator('conds', mode='before')
    @classmethod
    def _coerce_conds(cls, v):
        if isinstance(v, (list, tuple)):
            return tuple(v)
        return v

    @field_validator('targets', mode='before')
    @classmethod
    def _coerce_targets(cls, v):
        if isinstance(v, (list, tuple)):
            return tuple(_coerce_bid(t) for t in v)
        return v

    def __init__(self, *args, **kwargs):
        """Accept positional args: MCJump(conds, targets, loc=None)"""
        if args:
            if len(args) >= 1:
                kwargs.setdefault('conds', args[0])
            if len(args) >= 2:
                kwargs.setdefault('targets', args[1])
            if len(args) >= 3:
                kwargs.setdefault('loc', args[2])
        super().__init__(**kwargs)

    def __str__(self):
        items = []
        for cond, target in zip(self.conds, self.targets):
            items.append(f'{cond} ? {target}')
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

    def __init__(self, *args, **kwargs):
        """Accept positional args: Ret(exp, loc=None) with str/int coercion."""
        if args:
            if len(args) >= 1:
                kwargs.setdefault('exp', args[0])
            if len(args) >= 2:
                kwargs.setdefault('loc', args[1])
        # Coerce exp: str -> name2var, int -> Const
        exp = kwargs.get('exp')
        if isinstance(exp, str):
            kwargs['exp'] = name2var(exp, ctx=Ctx.LOAD)
        elif isinstance(exp, int) and not isinstance(exp, bool):
            kwargs['exp'] = Const(value=exp)
        super().__init__(**kwargs)

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
    args: tuple = ()
    ps: tuple = ()

    def __init__(self, *args_pos, **kwargs):
        """Accept positional args: Phi(var)"""
        if args_pos:
            if len(args_pos) >= 1:
                kwargs.setdefault('var', args_pos[0])
        # Set var.ctx = STORE to match old PHI behavior
        var = kwargs.get('var')
        if var is not None and hasattr(var, 'ctx') and var.ctx != Ctx.STORE:
            kwargs['var'] = var.model_copy(update={'ctx': Ctx.STORE})
        # Coerce list to tuple for args and ps
        if 'args' in kwargs and isinstance(kwargs['args'], list):
            kwargs['args'] = tuple(kwargs['args'])
        if 'ps' in kwargs and isinstance(kwargs['ps'], list):
            kwargs['ps'] = tuple(kwargs['ps'])
        super().__init__(**kwargs)

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

    def remove_arg(self, arg):
        """Remove an arg (and its corresponding ps entry) by identity. Returns a new Phi."""
        from ..common.utils import find_id_index
        idx = find_id_index(self.args, arg)
        new_args = self.args[:idx] + self.args[idx + 1:]
        if self.ps:
            assert len(self.args) == len(self.ps)
            new_ps = self.ps[:idx] + self.ps[idx + 1:]
            return self.model_copy(update={'args': new_args, 'ps': new_ps})
        return self.model_copy(update={'args': new_args})

    def reorder_args(self, indices):
        """Reorder args and ps by the given index sequence. Returns a new Phi."""
        args = tuple(self.args[idx] for idx in indices)
        ps = tuple(self.ps[idx] for idx in indices)
        return self.model_copy(update={'args': args, 'ps': ps})


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
    stms: tuple = ()

    def __str__(self):
        return 'mstm{{{}}}'.format(', '.join([str(stm) for stm in self.stms]))

    def __eq__(self, other):
        if not isinstance(other, MStm):
            return False
        return all(a == b for a, b in zip(self.stms, other.stms))

    def __hash__(self):
        return id(self)



# ============================================================
# Utility functions (previously in ir.py)
# ============================================================
def name2var(name: str, ctx: Ctx = Ctx.LOAD) -> IrVariable:
    """Convert a dot-separated name string to a Temp/Attr chain."""
    ss = name.split('.')
    if len(ss) == 1:
        return Temp(name=ss[0], ctx=ctx)
    exp = Temp(name=ss[0])
    for s in ss[1:-1]:
        exp = Attr(exp=exp, attr=s, name=s)
    exp = Attr(exp=exp, attr=ss[-1], name=ss[-1], ctx=ctx)
    return exp


def move_ir(src, dst):
    """Create a Move from src to dst, accepting strings/ints as convenience."""
    if isinstance(src, str):
        src = name2var(src, ctx=Ctx.LOAD)
    elif isinstance(src, int):
        src = Const(value=src)
    if isinstance(dst, str):
        dst = name2var(dst, ctx=Ctx.STORE)
    return Move(dst=dst, src=src)


def conds2str(conds):
    """Format a list of (exp, boolean) conditions as a string."""
    if conds:
        cs = []
        for exp, boolean in conds:
            cs.append(str(exp) + ' == ' + str(boolean))
        return ' and '.join(cs)
    else:
        return 'None'
