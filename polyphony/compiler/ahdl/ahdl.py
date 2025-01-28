from __future__ import annotations
import dataclasses
from dataclasses import dataclass, field
from typing import Optional, cast
from .signal import Signal
from ..ir.ir import Ctx
from ..common.utils import is_a

PYTHON_OP_2_HDL_OP_MAP = {
    'And': '&&', 'Or': '||',
    'Add': '+', 'Sub': '-', 'Mult': '*', 'FloorDiv': '//', 'Mod': '%',
    'LShift': '<<', 'RShift': '>>',
    'BitOr': '|', 'BitXor': '^', 'BitAnd': '&',
    'Eq': '==', 'NotEq': '!=', 'Lt': '<', 'LtE': '<=', 'Gt': '>', 'GtE': '>=',
    'Is': '==', 'IsNot': '!=',
    'USub': '-', 'UAdd': '+', 'Not': '!', 'Invert': '~'
}

class AHDL(object):
    '''Abstract HDL'''
    def is_a(self, cls):
        return is_a(self, cls)

    def find_ahdls(self, typ: type['AHDL']) -> list['AHDL']:
        ahdls = []

        def find_ahdls_rec(ahdl, typ, ahdls):
            #print(ahdl)
            if ahdl.is_a(typ):
                ahdls.append(ahdl)
            for k, v in ahdl.__dict__.items():
                if isinstance(v, AHDL):
                    if v is self:
                        continue
                    find_ahdls_rec(v, typ, ahdls)
                elif isinstance(v, list) or isinstance(v, tuple):
                    for elm in filter(lambda w:isinstance(w, AHDL),  v):
                        find_ahdls_rec(elm, typ, ahdls)
        find_ahdls_rec(self, typ, ahdls)
        return ahdls


@dataclass(frozen=True)
class AHDL_EXP(AHDL):
    pass


@dataclass(frozen=True)
class AHDL_CONST(AHDL_EXP):
    value: int | str

    def __str__(self):
        return f'{self.value}'

@dataclass(frozen=True, init=False)
class AHDL_OP(AHDL_EXP):
    op: str
    args: tuple[AHDL_EXP, ...]

    def __init__(self, op, *args):
        object.__setattr__(self, 'op', op)
        object.__setattr__(self, 'args', args)

    def __str__(self):
        if len(self.args) > 1:
            op = ' ' + PYTHON_OP_2_HDL_OP_MAP[self.op] + ' '
            str_args = [str(a) for a in self.args]
            return f'({op.join(str_args)})'
        else:
            return f'({PYTHON_OP_2_HDL_OP_MAP[self.op]}{self.args[0]})'

    def is_relop(self):
        return self.op in ('And', 'Or', 'Eq', 'NotEq', 'Lt', 'LtE', 'Gt', 'GtE', 'Is', 'IsNot')

    def is_unop(self):
        return self.op in ('USub', 'UAdd', 'Not', 'Invert')


@dataclass(frozen=True)
class AHDL_META_OP(AHDL_EXP):
    op: str
    args: tuple[AHDL_EXP, ...]

    def __init__(self, op, *args):
        object.__setattr__(self, 'op', op)
        object.__setattr__(self, 'args', args)

    def __str__(self):
        str_args = [str(a) for a in self.args]
        concat_args = ', '.join(str_args)
        return f'({self.op} {concat_args})'


@dataclass(frozen=True)
class AHDL_VAR(AHDL_EXP):
    vars: tuple[Signal]
    ctx: Ctx

    def __init__(self, var: Signal | tuple, ctx: Ctx):
        if isinstance(var, Signal):
            object.__setattr__(self, 'vars', (var,))
        else:
            assert var is not None
            object.__setattr__(self, 'vars', var)
        object.__setattr__(self, 'ctx', ctx)

    def __str__(self):
        return '.'.join([s.name for s in self.vars])

    @property
    def name(self) -> str:
        return str(self)

    @property
    def hdl_name(self) -> str:
        return '_'.join([s.name for s in self.vars])

    @property
    def sig(self) -> Signal:
        return self.vars[-1]

    def is_local_var(self) -> bool:
        return len(self.vars) == 1


@dataclass(frozen=True)
class AHDL_MEMVAR(AHDL_VAR):
    def __init__(self, var: Signal | tuple, ctx: Ctx):
        super().__init__(var, ctx)

    def __str__(self):
        return super().__str__() + f'[{self.vars[-1].width}]'


@dataclass(frozen=True)
class AHDL_SUBSCRIPT(AHDL_EXP):
    memvar: AHDL_VAR
    offset: AHDL_EXP

    @property
    def ctx(self):
        return self.memvar.ctx

    def __str__(self):
        return f'{self.memvar}[{self.offset}]'


@dataclass(frozen=True)
class AHDL_SYMBOL(AHDL_EXP):
    name: str

    def __str__(self):
        return self.name


@dataclass(frozen=True)
class AHDL_CONCAT(AHDL_EXP):
    varlist: tuple
    op: Optional[str]

    def __str__(self):
        if self.op:
            op = PYTHON_OP_2_HDL_OP_MAP[self.op]
        else:
            op = ', '
        concat_str = op.join([str(v) for v in self.varlist])
        return f'{{{concat_str}}}'


@dataclass(frozen=True)
class AHDL_SLICE(AHDL_EXP):
    var: AHDL_VAR
    hi: AHDL_EXP
    lo: AHDL_EXP

    def __str__(self):
        return f'{self.var}[{self.hi}:{self.lo}]'


@dataclass(frozen=True)
class AHDL_FUNCALL(AHDL_EXP):
    name: AHDL_VAR
    args: tuple[AHDL_EXP, ...]

    def __str__(self):
        args_str = ', '.join([str(arg) for arg in self.args])
        return f'{self.name}({args_str})'


@dataclass(frozen=True)
class AHDL_IF_EXP(AHDL_EXP):
    cond: AHDL_EXP
    lexp: AHDL_EXP
    rexp: AHDL_EXP

    def __str__(self):
        return f'{self.cond} ? {self.lexp} : {self.rexp}'


class AHDL_STM(AHDL):
    pass


@dataclass(frozen=True)
class AHDL_BLOCK(AHDL_STM):
    name: str
    codes: tuple[AHDL_STM, ...]

    def __post_init__(self):
        assert isinstance(self.codes, tuple)

    def __str__(self):
        s = '{\n'
        str_codes = '\n'.join([str(c) for c in self.codes])
        lines = ['  ' + line for line in str_codes.split('\n') if line]
        s += '\n'.join(lines)
        s += '\n}\n'
        return s

    def traverse(self):
        codes = []
        for c in self.codes:
            if c.is_a(AHDL_BLOCK):
                codes.extend(cast(AHDL_BLOCK, c).traverse())
            else:
                codes.append(c)
        return codes


@dataclass(frozen=True)
class AHDL_NOP(AHDL_STM):
    info: str

    def __str__(self):
        return f'nop(\'{self.info}\')'


@dataclass(frozen=True)
class AHDL_INLINE(AHDL_STM):
    code: str

    def __str__(self):
        return self.code


@dataclass(frozen=True)
class AHDL_MOVE(AHDL_STM):
    dst: AHDL_VAR | AHDL_SUBSCRIPT
    src: AHDL_EXP

    def __post_init__(self):
        if self.src.is_a(AHDL_VAR):
            assert cast(AHDL_VAR, self.src).ctx == Ctx.LOAD
        if self.dst.is_a(AHDL_VAR):
            assert cast(AHDL_VAR, self.dst).ctx == Ctx.STORE
        elif self.dst.is_a(AHDL_SUBSCRIPT):
            assert cast(AHDL_SUBSCRIPT, self.dst).memvar.ctx == Ctx.STORE
        else:
            assert False

    def __str__(self):
        if self.dst.is_a(AHDL_VAR) and cast(AHDL_VAR, self.dst).sig.is_net():
            return f'{self.dst} := {self.src}'
        return f'{self.dst} <= {self.src}'


class AHDL_DECL(AHDL_STM):
    pass


class AHDL_VAR_DECL(AHDL_DECL):
    pass


@dataclass(frozen=True)
class AHDL_ASSIGN(AHDL_VAR_DECL):
    dst: AHDL_VAR | AHDL_SUBSCRIPT
    src: AHDL_EXP
    name: str = field(init=False)

    def __post_init__(self):
        if self.src.is_a(AHDL_VAR):
            assert cast(AHDL_VAR, self.src).ctx == Ctx.LOAD
        if self.dst.is_a(AHDL_VAR):
            assert cast(AHDL_VAR, self.dst).ctx == Ctx.STORE
        elif self.dst.is_a(AHDL_SUBSCRIPT):
            assert cast(AHDL_SUBSCRIPT, self.dst).memvar.ctx == Ctx.STORE
        else:
            assert False
        # Use object.__setattr__ when writing to frozen fields after __init__
        # https://docs.python.org/3/library/dataclasses.html#frozen-instances
        object.__setattr__(self, 'name', str(self.dst))

    def __str__(self):
        return f'{self.dst} := {self.src}'


@dataclass(frozen=True)
class AHDL_FUNCTION(AHDL_VAR_DECL):
    output: AHDL_VAR
    inputs: tuple[AHDL_EXP, ...]
    stms: tuple[AHDL_STM, ...]
    name: str = field(init=False)

    def __post_init__(self):
        # Use object.__setattr__ when writing to frozen fields after __init__
        # https://docs.python.org/3/library/dataclasses.html#frozen-instances
        object.__setattr__(self, 'name', self.output.sig.name)

    def __str__(self):
        return f'function {self.output}'


@dataclass(frozen=True)
class AHDL_COMB(AHDL_VAR_DECL):
    name: str
    stms: tuple[AHDL_STM, ...]

    def __str__(self):
        return f'COMB {self.name}'


@dataclass(frozen=True)
class AHDL_EVENT_TASK(AHDL):
    events: tuple[tuple[Signal, str], ...]
    stm: AHDL_STM

    def __str__(self):
        events = ', '.join(f'{ev} {var}' for var, ev in self.events)
        return f'({events})\n{self.stm}'


@dataclass(frozen=True)
class AHDL_CONNECT(AHDL_STM):
    dst: AHDL_EXP
    src: AHDL_EXP

    def __str__(self):
        return f'{self.dst} = {self.src}'


@dataclass(frozen=True)
class AHDL_IO_READ(AHDL_STM):
    io: AHDL_VAR
    dst: Optional[AHDL_VAR]
    is_self: bool

    def __str__(self):
        if self.dst:
            return f'{self.dst} <= {self.io}.rd()'
        else:
            return f'{self.io}.rd()'


@dataclass(frozen=True)
class AHDL_IO_WRITE(AHDL_STM):
    io: AHDL_VAR
    src: AHDL_EXP
    is_self: bool

    def __str__(self):
        return f'{self.io}.wr({self.src})'


@dataclass(frozen=True)
class AHDL_SEQ(AHDL_STM):
    factor: AHDL_STM
    step: int
    step_n: int

    def __str__(self):
        return f'Sequence {self.step} : {self.factor}'


@dataclass(frozen=True)
class AHDL_IF(AHDL_STM):
    # ([cond], [code]) => if (cond) code
    # ([cond, None], [code1, code2]) => if (cond) code1 else code2
    conds: tuple[Optional[AHDL_EXP], ...]
    blocks: tuple[AHDL_BLOCK, ...]

    def __post_init__(self):
        assert len(self.conds) == len(self.blocks)
        assert self.conds[0]
        assert isinstance(self.conds, tuple)
        assert isinstance(self.blocks, tuple)

    def __str__(self):
        s = f'if {self.conds[0]}\n'
        s += str(self.blocks[0])
        for cond, ahdlblk in zip(self.conds[1:], self.blocks[1:]):
            if cond:
                s += f'elif {cond}\n'
                s += str(ahdlblk)
            else:
                s += 'else\n'
                s += str(ahdlblk)
        return s


@dataclass(frozen=True)
class AHDL_MODULECALL(AHDL_STM):
    scope: object  # TODO:
    args: tuple[AHDL_EXP, ...]
    instance_name: str
    prefix: str
    returns: tuple[AHDL_STM, ...]

    def __str__(self):
        args_str = ', '.join([str(arg) for arg in self.args])
        return f'{self.instance_name}({args_str})'


@dataclass(frozen=True)
class AHDL_CALLEE_PROLOG(AHDL_STM):
    name: str


@dataclass(frozen=True)
class AHDL_CALLEE_EPILOG(AHDL_STM):
    name: str


@dataclass(frozen=True)
class AHDL_PROCCALL(AHDL_STM):
    name: str
    args: tuple[AHDL_EXP, ...]

    def __str__(self):
        args_str = ', '.join([str(arg) for arg in self.args])
        return f'{self.name}({args_str})'


@dataclass(frozen=True, init=False)
class AHDL_META_WAIT(AHDL_STM):
    metaid: str
    args: tuple

    def __init__(self, metaid, *args):
        object.__setattr__(self, 'metaid', metaid)
        object.__setattr__(self, 'args', args)

    def __str__(self):
        items = []
        for arg in self.args:
            if isinstance(arg, (list, tuple)):
                items.append(', '.join([str(a) for a in arg]))
            else:
                items.append(str(arg))
        items_str = ', '.join(items)
        s = f'{self.metaid}({items_str})'
        return s


@dataclass(frozen=True)
class AHDL_CASE_ITEM(AHDL_STM):
    val: AHDL_EXP
    block: AHDL_BLOCK

    def __str__(self):
        return f'{self.val}:{self.block}'


@dataclass(frozen=True)
class AHDL_CASE(AHDL_STM):
    sel: AHDL_VAR
    items: tuple[AHDL_CASE_ITEM, ...]

    def __str__(self):
        return f'case {self.sel}\n' + '\n'.join([str(item) for item in self.items])


@dataclass(frozen=True)
class AHDL_TRANSITION(AHDL_STM):
    target_name: str

    def __post_init__(self):
        assert isinstance(self.target_name, str)

    def update_target(self, target_state_name: str):
        object.__setattr__(self, 'target_name', target_state_name)

    def is_empty(self):
        return self.target_name == ''

    def __str__(self):
        if self.target_name:
            name = self.target_name
        else:
            name = 'None'
        return f'goto {name}'


@dataclass(frozen=True)
class AHDL_TRANSITION_IF(AHDL_IF):
    pass


@dataclass(frozen=True)
class AHDL_PIPELINE_GUARD(AHDL_IF):
    def __init__(self, cond, codes):
        super().__init__((cond, ), (AHDL_BLOCK('', codes),))


@dataclass(frozen=True)
class State(AHDL):
    name: str
    block: AHDL_BLOCK
    step: int
    stg: object  # TODO

    def __str__(self):
        s = '---------------------------------\n'
        s += f'{self.name}:{self.step}\n'
        s += str(self.block)
        s += '\n'
        return s

    def traverse(self):
        return self.block.traverse()
