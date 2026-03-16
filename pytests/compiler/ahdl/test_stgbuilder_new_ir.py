"""Tests for STGBuilder new IR visit method aliases.

Verifies that AHDLTranslator and AHDLCombTranslator have the correct
PascalCase visit method aliases for new IR types, so they will work
when block.stms switches to new IR (ir.py).
"""
from polyphony.compiler.ahdl.stgbuilder import AHDLTranslator, AHDLCombTranslator


# Mapping: old IR class name -> new IR class name
VISIT_ALIASES = {
    'UnOp': 'UNOP',
    'BinOp': 'BINOP',
    'RelOp': 'RELOP',
    'CondOp': 'CONDOP',
    'Call': 'CALL',
    'New': 'NEW',
    'SysCall': 'SYSCALL',
    'Const': 'CONST',
    'MRef': 'MREF',
    'MStore': 'MSTORE',
    'Array': 'ARRAY',
    'Temp': 'TEMP',
    'Attr': 'ATTR',
    'Expr': 'EXPR',
    'CJump': 'CJUMP',
    'Jump': 'JUMP',
    'MCJump': 'MCJUMP',
    'Ret': 'RET',
    'Move': 'MOVE',
    'Phi': 'PHI',
    'UPhi': 'UPHI',
    'LPhi': 'LPHI',
    'CExpr': 'CEXPR',
    'CMove': 'CMOVE',
}


def test_ahdl_translator_has_new_ir_aliases():
    """AHDLTranslator has visit_<NewIRType> aliases for all visit_<OldIRType> methods."""
    for new_name, old_name in VISIT_ALIASES.items():
        old_method = getattr(AHDLTranslator, f'visit_{old_name}', None)
        new_method = getattr(AHDLTranslator, f'visit_{new_name}', None)
        if old_method is not None:
            assert new_method is not None, f'Missing alias visit_{new_name} for visit_{old_name}'
            assert new_method is old_method, f'visit_{new_name} is not the same as visit_{old_name}'


COMB_ALIASES = {
    'Call': 'CALL',
    'SysCall': 'SYSCALL',
    'New': 'NEW',
    'Temp': 'TEMP',
    'Attr': 'ATTR',
    'MRef': 'MREF',
    'MStore': 'MSTORE',
    'Array': 'ARRAY',
    'Expr': 'EXPR',
    'CJump': 'CJUMP',
    'MCJump': 'MCJUMP',
    'Jump': 'JUMP',
    'Ret': 'RET',
    'Move': 'MOVE',
    'Phi': 'PHI',
    'CExpr': 'CEXPR',
    'CMove': 'CMOVE',
}


def test_ahdl_comb_translator_has_new_ir_aliases():
    """AHDLCombTranslator has visit_<NewIRType> aliases for overridden methods."""
    for new_name, old_name in COMB_ALIASES.items():
        old_method = getattr(AHDLCombTranslator, f'visit_{old_name}', None)
        new_method = getattr(AHDLCombTranslator, f'visit_{new_name}', None)
        if old_method is not None:
            assert new_method is not None, f'Missing alias visit_{new_name} for visit_{old_name}'
            assert new_method is old_method, f'visit_{new_name} is not the same as visit_{old_name}'


def test_ahdl_translator_inherits_irvisitor_aliases():
    """AHDLTranslator inherits base visitor methods and has new IR aliases."""
    # These are inherited from IRVisitor but should still resolve via new IR names
    for new_name in ['UnOp', 'BinOp', 'RelOp', 'CondOp', 'Const', 'Temp', 'Attr']:
        assert hasattr(AHDLTranslator, f'visit_{new_name}'), f'Missing visit_{new_name} on AHDLTranslator'
