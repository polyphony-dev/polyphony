"""Tests for polyphony.compiler.ir.setlineno (LineNumberSetter and SourceDump)."""
import logging
from unittest.mock import MagicMock, patch
from polyphony.compiler.ir.setlineno import LineNumberSetter, SourceDump
from polyphony.compiler.ir.ir import Loc


class TestLineNumberSetterInit:
    def test_init(self):
        setter = LineNumberSetter()
        assert setter is not None


class TestSourceDumpInit:
    def test_init(self):
        dumper = SourceDump()
        assert dumper is not None


# Helper: create mock IR nodes with lineno attribute for testing
# LineNumberSetter visitor methods directly.

def _make_mock_exp(cls_name='Const'):
    """Create a mock IrExp-like object with the right class name."""
    m = MagicMock()
    m.__class__ = type(cls_name, (), {})
    m.lineno = -1
    return m


def _make_mock_stm(cls_name='Move', lineno=10):
    """Create a mock IrStm-like object."""
    m = MagicMock()
    m.__class__ = type(cls_name, (), {})
    m.lineno = lineno
    m.loc = Loc('test.py', lineno)
    return m


class TestLineNumberSetterVisitors:
    """Test LineNumberSetter visit methods by calling them directly
    with mock IR objects (bypassing scope traversal)."""

    def _make_setter(self, stm_lineno=10):
        setter = LineNumberSetter()
        setter.current_stm = _make_mock_stm('Move', stm_lineno)
        return setter

    def test_visit_UnOp(self):
        setter = self._make_setter()
        ir = MagicMock()
        ir.lineno = -1
        ir.exp = MagicMock()
        setter.visit_UnOp(ir)
        assert ir.lineno == setter.current_stm.lineno

    def test_visit_BinOp(self):
        setter = self._make_setter()
        ir = MagicMock()
        ir.lineno = -1
        ir.left = MagicMock()
        ir.right = MagicMock()
        setter.visit_BinOp(ir)
        assert ir.lineno == setter.current_stm.lineno

    def test_visit_RelOp(self):
        setter = self._make_setter()
        ir = MagicMock()
        ir.lineno = -1
        ir.left = MagicMock()
        ir.right = MagicMock()
        setter.visit_RelOp(ir)
        assert ir.lineno == setter.current_stm.lineno

    def test_visit_CondOp(self):
        setter = self._make_setter()
        ir = MagicMock()
        ir.lineno = -1
        ir.cond = MagicMock()
        ir.left = MagicMock()
        ir.right = MagicMock()
        setter.visit_CondOp(ir)
        assert ir.lineno == setter.current_stm.lineno

    def test_visit_Call(self):
        setter = self._make_setter()
        ir = MagicMock()
        ir.lineno = -1
        ir.func = MagicMock()
        ir.args = []
        ir.kwargs = {}
        setter.visit_Call(ir)
        assert ir.lineno == setter.current_stm.lineno

    def test_visit_SysCall(self):
        setter = self._make_setter()
        ir = MagicMock()
        ir.lineno = -1
        ir.func = MagicMock()
        ir.args = []
        ir.kwargs = {}
        setter.visit_SysCall(ir)
        assert ir.lineno == setter.current_stm.lineno

    def test_visit_New(self):
        setter = self._make_setter()
        ir = MagicMock()
        ir.lineno = -1
        ir.func = MagicMock()
        ir.args = []
        ir.kwargs = {}
        setter.visit_New(ir)
        assert ir.lineno == setter.current_stm.lineno

    def test_visit_Const(self):
        setter = self._make_setter()
        ir = MagicMock()
        ir.lineno = -1
        setter.visit_Const(ir)
        assert ir.lineno == setter.current_stm.lineno

    def test_visit_Temp(self):
        setter = self._make_setter()
        ir = MagicMock()
        ir.lineno = -1
        setter.visit_Temp(ir)
        assert ir.lineno == setter.current_stm.lineno

    def test_visit_Attr(self):
        setter = self._make_setter()
        ir = MagicMock()
        ir.lineno = -1
        ir.exp = MagicMock()
        setter.visit_Attr(ir)
        assert ir.lineno == setter.current_stm.lineno

    def test_visit_MRef(self):
        setter = self._make_setter()
        ir = MagicMock()
        ir.lineno = -1
        ir.mem = MagicMock()
        ir.offset = MagicMock()
        setter.visit_MRef(ir)
        assert ir.lineno == setter.current_stm.lineno

    def test_visit_MStore(self):
        setter = self._make_setter()
        ir = MagicMock()
        ir.lineno = -1
        ir.mem = MagicMock()
        ir.offset = MagicMock()
        ir.exp = MagicMock()
        setter.visit_MStore(ir)
        assert ir.lineno == setter.current_stm.lineno

    def test_visit_Array(self):
        setter = self._make_setter()
        ir = MagicMock()
        ir.lineno = -1
        ir.repeat = None
        ir.items = []
        setter.visit_Array(ir)
        assert ir.lineno == setter.current_stm.lineno

    def test_visit_Array_with_items(self):
        setter = self._make_setter()
        ir = MagicMock()
        ir.lineno = -1
        item1 = MagicMock()
        item2 = MagicMock()
        ir.repeat = MagicMock()
        ir.items = [item1, item2]
        setter.visit_Array(ir)
        assert ir.lineno == setter.current_stm.lineno

    def test_visit_Expr(self):
        setter = self._make_setter()
        ir = MagicMock()
        ir.lineno = 5
        ir.exp = MagicMock()
        setter.visit_Expr(ir)  # asserts lineno >= 0

    def test_visit_CJump(self):
        setter = self._make_setter()
        ir = MagicMock()
        ir.lineno = 5
        ir.exp = MagicMock()
        setter.visit_CJump(ir)

    def test_visit_MCJump(self):
        setter = self._make_setter()
        ir = MagicMock()
        ir.lineno = 5
        ir.conds = [MagicMock(), MagicMock()]
        setter.visit_MCJump(ir)

    def test_visit_Jump(self):
        setter = self._make_setter()
        ir = MagicMock()
        ir.lineno = 5
        setter.visit_Jump(ir)

    def test_visit_Ret(self):
        setter = self._make_setter()
        ir = MagicMock()
        ir.lineno = 5
        ir.exp = MagicMock()
        setter.visit_Ret(ir)

    def test_visit_Move(self):
        setter = self._make_setter()
        ir = MagicMock()
        ir.lineno = 5
        ir.src = MagicMock()
        ir.dst = MagicMock()
        setter.visit_Move(ir)

    def test_visit_Phi(self):
        setter = self._make_setter()
        ir = MagicMock()
        # Phi is a no-op
        setter.visit_Phi(ir)


class TestSourceDump:
    def test_process_block(self):
        """Test _process_block collects statements by loc."""
        from collections import defaultdict
        dumper = SourceDump()
        dumper.stms = defaultdict(list)

        mock_stm1 = MagicMock()
        mock_stm1.loc = Loc('test.py', 1)
        mock_stm2 = MagicMock()
        mock_stm2.loc = Loc('test.py', 2)

        mock_block = MagicMock()
        mock_block.stms = [mock_stm1, mock_stm2]

        dumper._process_block(mock_block)
        assert len(dumper.stms) == 2
        assert mock_stm1 in dumper.stms[Loc('test.py', 1)]
        assert mock_stm2 in dumper.stms[Loc('test.py', 2)]

    def test_process_block_same_loc(self):
        """Multiple statements at same location are grouped."""
        from collections import defaultdict
        dumper = SourceDump()
        dumper.stms = defaultdict(list)

        loc = Loc('test.py', 5)
        mock_stm1 = MagicMock()
        mock_stm1.loc = loc
        mock_stm2 = MagicMock()
        mock_stm2.loc = loc

        mock_block = MagicMock()
        mock_block.stms = [mock_stm1, mock_stm2]

        dumper._process_block(mock_block)
        assert len(dumper.stms[loc]) == 2
