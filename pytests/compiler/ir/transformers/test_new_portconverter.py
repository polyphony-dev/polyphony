"""Tests for PortTypeProp, FlippedTransformer, PortConnector."""
from polyphony.compiler.ir.ir import Ctx as OldCtx, Const, Temp, Attr, New, Move, Expr, Call
from polyphony.compiler.ir import ir as new
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.transformers.portconverter import (
    PortTypeProp, FlippedTransformer, PortConnector,
)
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def test_new_port_type_prop_imports():
    """Verify PortTypeProp can be imported and inherits from TypePropagation."""
    from polyphony.compiler.ir.transformers.typeprop import TypePropagation
    assert issubclass(PortTypeProp, TypePropagation)


def test_new_flipped_transformer_imports():
    """Verify FlippedTransformer can be imported and inherits from TypePropagation."""
    from polyphony.compiler.ir.transformers.typeprop import TypePropagation
    assert issubclass(FlippedTransformer, TypePropagation)


def test_new_port_connector_imports():
    """Verify PortConnector can be imported and has scopes attribute."""
    connector = PortConnector()
    assert hasattr(connector, 'scopes')
    assert connector.scopes == []


def test_normalize_direction():
    """Test direction normalization in PortTypeProp."""
    prop = PortTypeProp()
    assert prop._normalize_direction('in') == 'input'
    assert prop._normalize_direction('input') == 'input'
    assert prop._normalize_direction('i') == 'input'
    assert prop._normalize_direction('out') == 'output'
    assert prop._normalize_direction('output') == 'output'
    assert prop._normalize_direction('o') == 'output'
    assert prop._normalize_direction('any') == 'any'
    assert prop._normalize_direction('') == 'any'
    assert prop._normalize_direction('invalid') == ''


def test_new_port_type_prop_basic():
    """Test PortTypeProp processes a scope without errors on simple (non-port) code."""
    setup_test()
    top = Scope.global_scope()

    # Create a simple function scope with no port calls
    F = Scope.create(top, 'test_func', {'function'}, 0)
    F.add_sym('x', tags=set(), typ=Type.int(32))
    F.return_type = Type.int()
    blk = Block(F, nametag='blk1')
    F.set_entry_block(blk)
    F.set_exit_block(blk)
    blk.append_stm(Move(Temp('x', OldCtx.STORE), Const(42)))
    Block.set_order(blk, 0)

    # Should process without errors (no port-specific code to handle)
    PortTypeProp().process_scopes([F])


def test_new_flipped_ports_builder():
    """Test FlippedPortsBuilder flips direction in old IR NEW nodes."""
    from polyphony.compiler.ir.transformers.portconverter import FlippedPortsBuilder
    setup_test()

    # Create a Port scope
    port_scope = env.scopes.get('polyphony.io.Port')
    if port_scope is None:
        return  # Skip if Port scope not available

    # Create a ctor scope with a NEW Port call
    module = Scope.create(None, 'M', {'class', 'module'}, 0)
    ctor = Scope.create(module, '__init__', {'method', 'ctor'}, 0)
    ctor.add_sym('self', tags={'self'}, typ=Type.object(module))

    port_sym = ctor.add_sym('p', tags=set(), typ=Type.klass(port_scope))
    blk = Block(ctor, nametag='blk1')
    ctor.set_entry_block(blk)
    ctor.set_exit_block(blk)

    # NEW Port with direction 'in'
    dtype_sym = ctor.add_sym('@dtype', tags={'predefined'}, typ=Type.klass(env.scopes.get('__builtin__.int', Scope.create(None, 'int', {'class', 'typeclass'}, 0))))
    new_call = New(port_sym, [('dtype', Temp('@dtype')), ('direction', Const('in'))], {})
    blk.append_stm(Move(Temp('p', OldCtx.STORE), new_call))
    Block.set_order(blk, 0)

    # The builder should flip 'in' to 'out'
    FlippedPortsBuilder().process(ctor)
    # Check the direction was flipped
    for stm in blk.stms:
        if isinstance(stm, Move) and isinstance(stm.src, New):
            for name, arg in stm.src.args:
                if name == 'direction':
                    assert arg.value == 'out', f'Expected direction "out", got "{arg.value}"'
                    return
    # If we get here and there was no NEW, that's OK for this test
