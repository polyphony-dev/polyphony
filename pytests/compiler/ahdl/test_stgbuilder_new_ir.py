"""Tests for STGBuilder IR visit method names.

Verifies that AHDLTranslator and AHDLCombTranslator have PascalCase visit
methods for all IR types (IrVisitor convention).
"""
from polyphony.compiler.ahdl.stgbuilder import AHDLTranslator, AHDLCombTranslator


# PascalCase visit methods that AHDLTranslator should have
TRANSLATOR_METHODS = [
    'UnOp', 'BinOp', 'RelOp', 'CondOp',
    'Call', 'New', 'SysCall', 'Const',
    'MRef', 'MStore', 'Array', 'Temp', 'Attr',
    'Expr', 'CJump', 'Jump', 'MCJump', 'Ret', 'Move', 'Phi',
]


def test_ahdl_translator_has_new_ir_aliases():
    """AHDLTranslator has PascalCase visit methods for all IR types."""
    for name in TRANSLATOR_METHODS:
        method = getattr(AHDLTranslator, f'visit_{name}', None)
        assert method is not None, f'Missing visit_{name} on AHDLTranslator'


COMB_METHODS = [
    'Call', 'SysCall', 'New', 'Temp', 'Attr',
    'MRef', 'MStore', 'Array',
    'Expr', 'CJump', 'MCJump', 'Jump', 'Ret', 'Move', 'Phi',
    'CExpr', 'CMove',
]


def test_ahdl_comb_translator_has_new_ir_aliases():
    """AHDLCombTranslator has PascalCase visit methods for all IR types."""
    for name in COMB_METHODS:
        method = getattr(AHDLCombTranslator, f'visit_{name}', None)
        assert method is not None, f'Missing visit_{name} on AHDLCombTranslator'


def test_ahdl_translator_inherits_irvisitor_aliases():
    """AHDLTranslator inherits base visitor methods from IrVisitor."""
    for name in ['UnOp', 'BinOp', 'RelOp', 'CondOp', 'Const', 'Temp', 'Attr']:
        assert hasattr(AHDLTranslator, f'visit_{name}'), f'Missing visit_{name} on AHDLTranslator'
