import inspect
import types
import operator
import os
from .compiler.common.common import Tagged
from .compiler.common.common import get_src_text
from .compiler.ahdl.ahdl import *
from .compiler.ahdl.ahdlvisitor import AHDLVisitor
from .compiler.ahdl.signal import Signal
from .compiler.ahdl.hdlscope import HDLScope
from .compiler.ahdl.hdlmodule import HDLModule
from .compiler.ir.ir import Ctx
from .compiler.ir.symbol import Symbol


class HDLAssertionError(AssertionError):
    pass


def twos_comp(val, bits):
    """compute the 2's complement of int value val"""
    if (val & (1 << (bits - 1))) != 0: # if sign bit is set e.g., 8bit: 128-255
        val = val - (1 << bits)        # compute negative value
    return val                         # return positive value as is

class Value(Tagged):
    TAGS = Signal.TAGS
    def __init__(self, val, width, sign, signal):
        if signal:
            super().__init__(signal.tags)
        else:
            super().__init__(set())
        self.width = width
        self.sign = sign
        self.signal = signal
        self.val = 'X'
        self.set(val)

    def set(self, v):
        if isinstance(v, int):
            mask = (1 << self.width) - 1
            val = v & mask
            if self.sign:
                new_val = twos_comp(val, self.width)
            else:
                new_val = val
        elif isinstance(v, str):
            new_val = v
        is_update = self.val != new_val
        self.val = new_val
        return is_update

    def get(self):
        return self.val

    def toInteger(self):
        return Integer(self.val, self.width, self.sign)


class Integer(Value):
    def __init__(self, val, width, sign):
        super().__init__(val, width, sign, None)

    def __str__(self):
        return str(self.val)

    def __repr__(self):
        return f'Integer[{self.width}]={self.val}'

    def __bin_op__(self, op, rhs):
        if self.val == 'X' or rhs.val == 'X':
            return Integer('X', 0, False)
        width = self.width + rhs.width
        sign = max(self.sign, rhs.sign)
        value = op(self.val, rhs.val)
        return Integer(value, width, sign)

    def __add__(self, rhs):
        return self.__bin_op__(operator.add, rhs)

    def __sub__(self, rhs):
        return self.__bin_op__(operator.sub, rhs)

    def __mul__(self, rhs):
        return self.__bin_op__(operator.mul, rhs)

    def __floordiv__(self, rhs):
        return self.__bin_op__(operator.floordiv, rhs)

    def __mod__(self, rhs):
        return self.__bin_op__(operator.mod, rhs)

    def __bit_op__(self, op, rhs):
        if self.val == 'X' or rhs.val == 'X':
            return Integer('X', 0, False)
        width = max(self.width, rhs.width)
        value = op(self.val, rhs.val)
        return Integer(value, width, False)

    def __and__(self, rhs):
        return self.__bit_op__(operator.and_, rhs)

    def __or__(self, rhs):
        return self.__bit_op__(operator.or_, rhs)

    def __xor__(self, rhs):
        return self.__bit_op__(operator.xor, rhs)

    def __eq__(self, rhs):
        b = self.val == rhs.val
        return Integer(int(b), 1, False)

    def __ne__(self, rhs):
        b = self.val != rhs.val
        return Integer(int(b), 1, False)

    def __lt__(self, rhs):
        if self.val == 'X' or rhs.val == 'X':
            return Integer('X', 0, False)
        b = self.val < rhs.val
        return Integer(int(b), 1, False)

    def __le__(self, rhs):
        if self.val == 'X' or rhs.val == 'X':
            return Integer('X', 0, False)
        b = self.val <= rhs.val
        return Integer(int(b), 1, False)

    def __gt__(self, rhs):
        if self.val == 'X' or rhs.val == 'X':
            return Integer('X', 0, False)
        b = self.val > rhs.val
        return Integer(int(b), 1, False)

    def __ge__(self, rhs):
        if self.val == 'X' or rhs.val == 'X':
            return Integer('X', 0, False)
        b = self.val >= rhs.val
        return Integer(int(b), 1, False)

    def __lshift__(self, rhs):
        if self.val == 'X' or rhs.val == 'X':
            return Integer('X', 0, False)
        if rhs.val > self.width or rhs.val < 0:
            return Integer(0, self.width, self.sign)
        v = self.val << rhs.val
        return Integer(v, self.width, self.sign)

    def __rshift__(self, rhs):
        if self.val == 'X' or rhs.val == 'X':
            return Integer('X', 0, False)
        if rhs.val > self.width or rhs.val < 0:
            return Integer(0, self.width, self.sign)
        v = self.val >> rhs.val
        return Integer(v, self.width, self.sign)

    def __bool__(self):
        if self.val == 'X':
            return False
        return bool(self.val)

    def __int__(self):
        if self.val == 'X':
            return None
        return self.val

    def __pos__(self):
        return self

    def __neg__(self):
        if self.val == 'X':
            return self
        return Integer(-self.val, self.width, self.sign)

    def __invert__(self):
        if self.val == 'X':
            return self
        return Integer(~self.val, self.width, self.sign)

class Net(Value):
    def __init__(self, val, width, signal):
        super().__init__(val, width, signal.is_int(), signal)

    def __str__(self):
        return str(self.val)

    def __repr__(self):
        return f'Net(\'{self.signal}\')={self.val}'

class Reg(Value):
    def __init__(self, val, width, signal):
        super().__init__(val, width, signal.is_int(), signal)
        self.val = 'X'
        self.prev_val = 'X'

    def __str__(self):
        return str(self.val)

    def __repr__(self):
        return f'Reg(\'{self.signal}\')={self.val}'

    def set(self, v):
        if isinstance(v, int):
            mask = (1 << self.width) - 1
            val = v & mask
        else:
            val = v
        if self.sign and isinstance(v, int):
            new_next = twos_comp(val, self.width)
        else:
            new_next = val
        is_update = self.val != new_next
        self.next = new_next
        return is_update

    def update(self):
        self.prev_val = self.val
        self.val = self.next


current_simulator = None

def clkfence():
    if current_simulator is None:
        raise RuntimeError()
    current_simulator._period()

def clksleep(n):
    if current_simulator is None:
        raise RuntimeError()
    current_simulator._period(n)

def clktime():
    if current_simulator is None:
        raise RuntimeError()
    return current_simulator.clock_time

def clkrange(n):
    if current_simulator is None:
        raise RuntimeError()
    if n:
        for i in range(n):
            current_simulator._period()
            yield i
        current_simulator._period()


class Port(object):
    def __init__(self, dtype, direction, init=None, **kwargs):
        self.value = None

    def _set_value(self, value):
        assert isinstance(value, (Net, Reg))
        self.value = value

    def wr(self, v):
        if not self.value.signal.is_input():
            raise RuntimeError()
        self.value.set(v)

    def rd(self):
        if not self.value.signal.is_output():
            raise RuntimeError()
        return self.value.get()

    def set(self, v):
        return self.value.set(v)

    def toInteger(self):
        return self.value.toInteger()

    def __str__(self):
        return str(self.value)

    def __repr__(self):
        return f'Port(\'{repr(self.value)}\')'

    def edge(self, old_v, new_v):
        assert isinstance(self.value, Reg)
        return self.value.prev_val == old_v and self.value.val == new_v

    @property
    def signal(self):
        return self.value.signal


class Simulator(object):
    def __init__(self, model):
        if isinstance(model, list):
            self.models = [getattr(m, '__model') for m in model]
        elif isinstance(model, Model):
            self.models = [getattr(model, '__model')]
        else:
            assert False

        self.evaluators = [ModelEvaluator(model) for model in self.models]
        self.clock_time = 0

    def __enter__(self):
        self.begin()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.end()

    def begin(self):
        global current_simulator
        if current_simulator is not None:
            raise RuntimeError()
        current_simulator = self
        self._reset()
        self.clock_time = 0

    def end(self):
        global current_simulator
        if current_simulator is None:
            raise RuntimeError()
        current_simulator = None

    def _period(self, count=1):
        for i in range(count):
            for model in self.models:
                model.clk.val = 1
            for evaluator in self.evaluators:
                evaluator.eval()
            self.clock_time += 1
            for model in self.models:
                model.clk.val = 0

    def _reset(self, count=1):
        for model in self.models:
            model.rst.val = 1
        self._period(count)
        for model in self.models:
            model.rst.val = 0
        self.clock_time = 0


class ModelEvaluator(AHDLVisitor):
    def __init__(self, model):
        assert isinstance(model, types.SimpleNamespace)
        self.model = model
        self.updated_sigs = set()


    def visit(self, ahdl):
        # if ahdl.is_a(AHDL_STM):
        #     print('eval', ahdl)
        return super().visit(ahdl)

    def eval(self):
        for task in self.model._tasks:
            self.visit(task)
        self._update_regs()
        self._eval_decls()

    def _eval_decls(self):
        self.updated_sigs.add(None)
        while self.updated_sigs:
            self.updated_sigs.clear()
            for decl in self.model._decls:
                self.visit(decl)

    def _find_model(self, ahdl):
        assert isinstance(ahdl, AHDL_VAR)
        model = self.model
        for v in ahdl.vars[:-1]:
            if v.is_subscope():
                user_model = getattr(model, v.name)
                model = getattr(user_model, '__model')
        assert isinstance(model, types.SimpleNamespace)
        return model

    def _collect_model(self, model):
        models = [model]
        for v in vars(model).values():
            if isinstance(v, Model):
                model_core = getattr(v, '__model')
                models.extend(self._collect_model(model_core))
        return models

    def _update_regs(self):
        models = self._collect_model(self.model)
        for model in models:
            regs = [x for x in vars(model).values() if isinstance(x, Reg)]
            for reg in regs:
                reg.update()
            regarrays = [x for x in vars(model).values() if isinstance(x, tuple) and isinstance(x[0], Reg)]
            for regarray in regarrays:
                for reg in regarray:
                    reg.update()
            regs = [x.value for x in vars(model).values() if isinstance(x, Port) and isinstance(x.value, Reg)]
            for reg in regs:
                reg.update()

    def visit_AHDL_CONST(self, ahdl):
        if isinstance(ahdl.value, int):
            return Integer(ahdl.value, width=32, sign=True)
        elif isinstance(ahdl.value, str):
            return Value(ahdl.value, width=0, sign=False, signal=None)
        else:
            assert False

    def visit_AHDL_VAR(self, ahdl):
        model = self._find_model(ahdl)
        v = getattr(model, ahdl.sig.name)
        assert v is not None
        assert isinstance(v, (Reg, Net, Integer, Port))
        if ahdl.ctx is Ctx.LOAD:
            v = v.toInteger()
        return v

    def visit_AHDL_MEMVAR(self, ahdl):
        model = self._find_model(ahdl)
        mem = getattr(model, ahdl.sig.name)
        assert mem
        assert isinstance(mem, tuple)
        return mem

    def visit_AHDL_SUBSCRIPT(self, ahdl):
        mem = self.visit(ahdl.memvar)
        assert isinstance(mem, tuple)
        offs = self.visit(ahdl.offset)
        assert isinstance(offs, Integer)
        if offs.get() == 'X':
            return Integer('X', 1, False)
        mem_offs = offs.get()
        if mem_offs < 0 or mem_offs >= len(mem):
            return Integer('X', 1, False)
        v = mem[mem_offs]
        assert isinstance(v, (Reg, Net))
        if ahdl.memvar.ctx is Ctx.LOAD:
            v = v.toInteger()
        return v

    def eval_binop(self, op, left, right):
        l = self.visit(left)
        r = self.visit(right)
        assert isinstance(l, Integer)
        assert isinstance(r, Integer)
        if l.val == 'X' or r.val == 'X':
            return Integer('X', 0, False)
        if op == 'Add':
            return l + r
        elif op == 'Sub':
            return l - r
        elif op == 'Mult':
            return l * r
        elif op == 'FloorDiv':
            return l // r
        elif op == 'Mod':
            return l % r
        elif op == 'LShift':
            return l << r
        elif op == 'RShift':
            return l >> r
        elif op == 'BitOr':
            return l | r
        elif op == 'BitXor':
            return l ^ r
        elif op == 'BitAnd':
            return l & r
        else:
            assert False

    def eval_relop(self, op, left, right):
        l = self.visit(left)
        r = self.visit(right)
        assert isinstance(l, Integer)
        assert isinstance(r, Integer)
        if op == 'And':
            if l.val and r.val:
                return Integer(1, 1, False)
            else:
                return Integer(0, 1, False)
        elif op == 'Or':
            if l.val or r.val:
                return Integer(1, 1, False)
            else:
                return Integer(0, 1, False)
        elif op == 'Eq':
            return l == r
        elif op == 'NotEq':
            return l != r
        elif op == 'Lt':
            return l < r
        elif op == 'LtE':
            return l <= r
        elif op == 'Gt':
            return l > r
        elif op == 'GtE':
            return l >= r
        elif op == 'Is':
            return l == r
        elif op == 'IsNot':
            return l != r

    def eval_unop(self, op, arg):
        a = self.visit(arg)
        assert isinstance(a, Integer)
        if op == 'USub':
            return -a
        elif op == 'UAdd':
            return a
        elif op == 'Not':
            return Integer(not a.get(), 1, False)
        elif op == 'Invert':
            return ~a


    def visit_AHDL_OP(self, ahdl):
        if ahdl.is_unop():
            a = self.eval_unop(ahdl.op, ahdl.args[0])
            return a
        elif ahdl.is_relop():
            lhs = ahdl.args[0]
            for rhs in ahdl.args[1:]:
                lhs = self.eval_relop(ahdl.op, lhs, rhs)
                assert isinstance(lhs, Integer)
            return lhs
        else:
            lhs = ahdl.args[0]
            for rhs in ahdl.args[1:]:
                lhs = self.eval_binop(ahdl.op, lhs, rhs)
                assert isinstance(lhs, Integer)
            return lhs

    def visit_AHDL_META_OP(self, ahdl):
        for a in ahdl.args:
            if isinstance(a, AHDL):
                self.visit(a)

    def visit_AHDL_SYMBOL(self, ahdl):
        if ahdl.name == "'bz":
            return Integer('X', 1, False)
        assert False

    def visit_AHDL_CONCAT(self, ahdl):
        for var in ahdl.varlist:
            self.visit(var)

    def visit_AHDL_SLICE(self, ahdl):
        self.visit(ahdl.var)
        self.visit(ahdl.hi)
        self.visit(ahdl.lo)

    def visit_AHDL_NOP(self, ahdl):
        pass

    def visit_AHDL_INLINE(self, ahdl):
        pass

    def visit_AHDL_MOVE(self, ahdl):
        src = self.visit(ahdl.src)
        dst = self.visit(ahdl.dst)
        assert isinstance(src, Integer)
        if isinstance(dst, (Reg, Port)):
            # print(f'{dst.signal.name} = {src}')
            dst.set(src.get())

    def visit_AHDL_IO_READ(self, ahdl):
        self.visit(ahdl.io)
        if ahdl.dst:
            self.visit(ahdl.dst)

    def visit_AHDL_IO_WRITE(self, ahdl):
        self.visit(ahdl.io)
        self.visit(ahdl.src)

    def visit_AHDL_SEQ(self, ahdl):
        method = 'visit_{}'.format(ahdl.factor.__class__.__name__)
        visitor = getattr(self, method, None)
        return visitor(ahdl.factor)

    def visit_AHDL_IF(self, ahdl):
        cvs = []
        for cond, blk in zip(ahdl.conds, ahdl.blocks):
            if cond:
                cv = self.visit(cond)
                assert isinstance(cv, Integer)
                # print(f'if {cond} == {cv}')
                assert cv.val != 'X'
                if int(cv.val):
                    self.visit(blk)
                    break
            else:
                self.visit(blk)
                break

    def visit_AHDL_IF_EXP(self, ahdl):
        cv = self.visit(ahdl.cond)
        assert isinstance(cv, Integer)
        assert cv.val != 'X'
        if int(cv.val):
            return self.visit(ahdl.lexp)
        else:
            return self.visit(ahdl.rexp)

    def visit_AHDL_CASE(self, ahdl):
        state_val = self.visit(ahdl.sel)
        # print(f'case {ahdl.sel} == {state_val}')
        for item in ahdl.items:
            case_val = self.visit(item.val)
            if state_val.get() == case_val.get():
                self.visit(item.block)
                break

    def visit_AHDL_CASE_ITEM(self, ahdl):
        self.visit(ahdl.block)

    def visit_AHDL_MODULECALL(self, ahdl):
        for arg in ahdl.args:
            self.visit(arg)

    def visit_AHDL_CALLEE_PROLOG(self, ahdl):
        pass

    def visit_AHDL_CALLEE_EPILOG(self, ahdl):
        pass

    def visit_AHDL_FUNCALL(self, ahdl):
        func = None
        for f in self.model.hdlmodule.functions:
            if f.output.sig == ahdl.name.sig:
                func = f
                break
        else:
            assert False

        for arg, input in zip(ahdl.args, func.inputs):
            arg_val = self.visit(arg)
            input_net = getattr(self.model, input.sig.name)
            input_net.set(arg_val.get())
        output = self.visit(func)
        return output.toInteger()

    def visit_AHDL_PROCCALL(self, ahdl):
        args = [self.visit(arg) for arg in ahdl.args]
        if ahdl.name == '!hdl_print':
            argvs = [arg.get() for arg in args]
            print(*argvs)
        elif ahdl.name == '!hdl_assert':
            if not bool(args[0]):
                src_text = self._get_source_text(ahdl)
                raise HDLAssertionError(src_text)
        else:
            raise RuntimeError('unknown function', ahdl.name)

    def visit_AHDL_META(self, ahdl):
        method = 'visit_' + ahdl.metaid
        visitor = getattr(self, method, None)
        if visitor:
            return visitor(ahdl)

    def visit_AHDL_META_WAIT(self, ahdl):
        for arg in ahdl.args:
            if isinstance(arg, AHDL):
                self.visit(arg)

    def visit_AHDL_TRANSITION(self, ahdl):
        assert False

    def visit_AHDL_TRANSITION_IF(self, ahdl):
        self.visit_AHDL_IF(ahdl)

    def visit_AHDL_PIPELINE_GUARD(self, ahdl):
        self.visit_AHDL_IF(ahdl)

    def visit_AHDL_BLOCK(self, ahdl):
        for c in ahdl.codes:
            self.visit(c)

    def visit_AHDL_ASSIGN(self, ahdl):
        src = self.visit(ahdl.src)
        dst = self.visit(ahdl.dst)
        assert isinstance(src, Integer)
        assert isinstance(dst, (Net, Port))
        is_update = dst.set(src.get())
        if is_update:
            self.updated_sigs.add(ahdl.dst.sig)

    def visit_AHDL_EVENT_TASK(self, ahdl):
        triggered = False
        for v, e in ahdl.events:
            sig = getattr(self.model, v.name)
            if e == 'rising' and sig.val == 1:
                triggered = True
                break
            elif e == 'falling' and sig.val == 0:
                triggered = True
                break
        if triggered:
            self.visit(ahdl.stm)

    def visit_AHDL_FUNCTION(self, ahdl):
        for stm in ahdl.stms:
            self.visit(stm)
        return self.visit(ahdl.output)

    def visit_AHDL_CONNECT(self, ahdl):
        src = self.visit(ahdl.src)
        dst = self.visit(ahdl.dst)
        dst.set(src.get())

    def _get_source_text(self, ahdl):
        _, node = self.model.hdlmodule.ahdl2dfgnode[id(ahdl)]
        if node.tag.loc.lineno < 1:
            return
        text = get_src_text(node.tag.loc.filename, node.tag.loc.lineno)
        text = text.strip()
        if not text:
            return
        if text[-1] == '\n':
            text = text[:-1]
        filename = os.path.basename(node.tag.loc.filename)
        return f'{filename} [{node.tag.loc.lineno}]: {text}'


class Model(object):
    def __getattribute__(self, name):
        model_core = super().__getattribute__('__model')
        if name == '__model':
            return model_core
        if name == '__dict__':
            di = {}
            for name, v in vars(model_core).items():
                if isinstance(v, Port):
                    di[name] = v
            return di
        attr = getattr(model_core, name)
        if not attr:
            raise AttributeError()
        if isinstance(attr, Port):
            return attr
        if isinstance(attr, Value):
            return attr.get()
        if callable(attr):
            return attr
        if hasattr(attr, 'interface_tag'):
            return attr
        raise AttributeError()

    def __setattr__(self, name, value) -> None:
        model_core = super().__getattribute__('__model')
        attr = getattr(model_core, name)
        if not attr:
            raise AttributeError()
        if isinstance(attr, Value):
            return attr.set(value)
        if isinstance(attr, Port):
            raise AttributeError('Cannot set to port')
        raise AttributeError()

    def __call__(self, *args, **kwargs):
        model_core = super().__getattribute__('__model')
        if hasattr(model_core, '_call_body'):
            return model_core._call_body(*args, **kwargs)
        else:
            return self

class SimulationModelBuilder(object):
    def build_model(self, hdlmodule: HDLScope, main_py_module, is_top=False):
        core_model = self.build_core(hdlmodule, main_py_module, is_top)
        user_model = Model()
        super(Model, user_model).__setattr__('__model', core_model)
        return user_model

    def build_core(self, hdlmodule: HDLScope, main_py_module, is_top):
        model = types.SimpleNamespace()
        for sig, subscope in hdlmodule.subscopes.items():
            sub = self.build_model(subscope, main_py_module)
            setattr(model, sig.name, sub)

        model.hdlmodule = hdlmodule
        if is_top: # isinstance(hdlmodule, HDLModule):
            model._tasks = hdlmodule.tasks
            model._decls = hdlmodule.decls
        else:
            model._tasks = []
            model._decls = []
        if hdlmodule.scope.is_function_module():
            self.build_function(hdlmodule, model)
        else:
            self.build_module(hdlmodule, model, main_py_module, is_top)
        return model

    def build_function(self, hdlscope: HDLScope, model):
        self._add_signals(hdlscope, model)
        self._add_function_call(hdlscope, model)
        self._make_io_object_for_function(hdlscope, model)
        if isinstance(hdlscope, HDLModule):
            self._make_rom_function(hdlscope, model)

    def build_module(self, hdlscope: HDLScope, model, main_py_module, is_top):
        self._add_signals(hdlscope, model)
        self._make_io_object_for_module(hdlscope, model)
        self._add_io_method(model, main_py_module)
        if isinstance(hdlscope, HDLModule):
            self._make_rom_function(hdlscope, model)

    def _add_signals(self, hdlscope: HDLScope, model):
        for sig in hdlscope.get_signals({'constant', 'reg', 'net', 'regarray', 'netarray', 'rom'}, {'input', 'output'}):
            if sig.is_constant():
                val = hdlscope.constants[sig]
                setattr(model, sig.name, Integer(val, sig.width, sign=sig.is_int()))
                continue
            elif sig.is_reg():
                val = int(sig.init_value) if sig.is_initializable() else 0
                if sig.width > 0:
                    setattr(model, sig.name, Reg(val, sig.width, sig))
                continue
            elif sig.is_net():
                setattr(model, sig.name, Net(0, sig.width, sig))
                continue
            elif sig.is_regarray():
                val = int(sig.init_value) if sig.is_initializable() else 0
                xs = [Reg(val, sig.width[0], sig) for _ in range(sig.width[1])]
                setattr(model, sig.name, tuple(xs))
                continue
            elif sig.is_netarray():
                assert False
            elif sig.is_rom():
                continue
            assert False

    def get_input_signals(self, hdlscope: HDLScope):
        return [sig for sig in hdlscope.get_signals({'input'})]

    def get_output_signals(self, hdlscope: HDLScope):
        return [sig for sig in hdlscope.get_signals({'output'})]

    def _make_io_object_for_module(self, hdlscope: HDLScope, model):
        # add IO ports
        in_sigs = self.get_input_signals(hdlscope)
        out_sigs = self.get_output_signals(hdlscope)
        for sig in in_sigs:
            if sig.name in ('clk', 'rst'):
                continue
            input_value = Reg(0, sig.width, sig)
            iport = Port(None, None, None)
            iport._set_value(input_value)
            setattr(model, sig.name, iport)
        for sig in out_sigs:
            if sig.is_reg():
                val = int(sig.init_value) if sig.is_initializable() else 0
                output_value = Reg(val, sig.width, sig)
            elif sig.is_net():
                output_value = Net(0, sig.width, sig)
            oport = Port(None, None, None)
            oport._set_value(output_value)
            setattr(model, sig.name, oport)
        if isinstance(hdlscope, HDLModule):
            # add clk and rst
            clksig = hdlscope.signal('clk')
            assert isinstance(clksig, Signal)
            setattr(model, clksig.name, Reg(0, clksig.width, clksig))
            rstsig = hdlscope.signal('rst')
            assert isinstance(rstsig, Signal)
            setattr(model, rstsig.name, Reg(0, rstsig.width, rstsig))

    def _make_io_object_for_function(self, hdlscope: HDLScope, model):
        for sig in hdlscope.get_signals({'input', 'output'}):
            if sig.is_input():
                assert sig.is_net()
                # Input is of type net, but generated as Reg for simulation
                input_object = Reg(0, sig.width, sig)
                if sig.is_single_port():
                    input_object = Port(input_object)
                setattr(model, sig.name, input_object)
            elif sig.is_output():
                if sig.is_reg():
                    val = int(sig.init_value) if sig.is_initializable() else 0
                    output_object = Reg(val, sig.width, sig)
                elif sig.is_net():
                    output_object = Net(0, sig.width, sig)
                if sig.is_single_port():
                    output_object = Port(output_object)
                setattr(model, sig.name, output_object)

    def _add_io_method(self, model, main_py_module):
        def find_origin_scope(scope):
            if scope.origin:
                return find_origin_scope(scope.origin)
            return scope
        origin_scope = find_origin_scope(model.hdlmodule.scope)
        py_name = origin_scope.base_name
        if py_name in main_py_module.__dict__:
            py_class = main_py_module.__dict__[py_name]
        else:
            # Handling of cases where a class is renamed with 'import as'
            classes = {v.__name__: v for k, v in main_py_module.__dict__.items() if inspect.isclass(v)}
            if py_name in classes:
                py_class = classes[py_name]
        for name, attr in vars(py_class).items():
            if name.startswith("__"):
                continue
            if not callable(attr):
                continue
            for sym_name, sym in origin_scope.symbols.items():
                if sym_name.startswith(name):
                    func_scope = find_origin_scope(sym.typ.scope)
                    if func_scope.base_name == name:
                        break
            if func_scope.is_worker():
                continue
            # we need to bind the function to the model instance
            setattr(model, name, types.MethodType(attr, model))

    def convert_py_interface_to_hdl_interface(self):
        pass

    def _add_function_call(self, hdlscope: HDLScope, model):
        def _funcall(model, fn_name, args):
            ready  = getattr(model, f'{fn_name}_ready')
            valid  = getattr(model, f'{fn_name}_valid')
            accept = getattr(model, f'{fn_name}_accept')
            if hasattr(model, f'{fn_name}_out_0'):
                out = getattr(model, f'{fn_name}_out_0')
            else:
                out = None

            ready.set(1)
            for name, value in args:
                i = getattr(model, f'{fn_name}_in_{name}')
                i.set(value)
            clkfence()

            while valid.get() != 1:
                clkfence()
            ready.set(0)

            if out:
                out_value = out.get()
            else:
                out_value = None
            accept.set(1)
            clkfence()

            accept.set(0)
            clkfence()
            return out_value

        def call_body(*args, **kwargs):
            arg_and_names = []
            param_names = hdlscope.scope.param_names()
            default_values = hdlscope.scope.param_default_values()
            for i, v in enumerate(args):
                arg_and_names.append((param_names[i], v))
            for k, v in kwargs.items():
                arg_and_names.append((k, v))
            for param_name, defval in list(zip(param_names, default_values))[len(arg_and_names):]:
                arg_and_names.append((param_name, defval.value))
            return _funcall(model, hdlscope.name, arg_and_names)

        setattr(model, '_call_body', call_body)

    def _make_rom_function(self, hdlmodule: HDLModule, model):
        for fn in hdlmodule.functions:
            for i in fn.inputs:
                assert not hasattr(model, i.sig.name)
                setattr(model, i.sig.name, Net(0, i.sig.width, i.sig))
            assert not hasattr(model, fn.output.hdl_name)
            setattr(model, fn.output.hdl_name, Net(0, fn.output.sig.width[0], fn.output.sig))
