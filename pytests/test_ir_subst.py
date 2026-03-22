from polyphony.compiler.ir.ir import Temp, Move, Phi, Const, Ctx


def test_subst_by_id_basic():
    """subst_by_id replaces nodes matched by identity."""
    src = Temp(name='x', ctx=Ctx.LOAD)
    dst = Temp(name='y', ctx=Ctx.STORE)
    stm = Move(dst=dst, src=src)
    new_src = Temp(name='x#1', ctx=Ctx.LOAD)
    rename_map = {id(src): new_src}
    new_stm = stm.subst_by_id(rename_map)
    assert new_stm is not stm
    assert new_stm.src.name == 'x#1'
    assert new_stm.dst is dst  # untouched


def test_subst_by_id_phi_args():
    """subst_by_id renames vars inside Phi.args."""
    var = Temp(name='x', ctx=Ctx.STORE)
    arg0 = Temp(name='x', ctx=Ctx.LOAD)
    arg1 = Temp(name='x', ctx=Ctx.LOAD)
    phi = Phi(var=var, args=(arg0, arg1))
    new_arg0 = Temp(name='x#1', ctx=Ctx.LOAD)
    rename_map = {id(arg0): new_arg0}
    new_phi = phi.subst_by_id(rename_map)
    assert new_phi.args[0].name == 'x#1'
    assert new_phi.args[1] is arg1  # untouched


def test_subst_by_id_no_match():
    """subst_by_id returns same object when nothing matches."""
    src = Temp(name='x', ctx=Ctx.LOAD)
    dst = Temp(name='y', ctx=Ctx.STORE)
    stm = Move(dst=dst, src=src)
    other = Temp(name='z', ctx=Ctx.LOAD)
    rename_map = {id(other): Temp(name='z#1', ctx=Ctx.LOAD)}
    result = stm.subst_by_id(rename_map)
    assert result is stm  # unchanged
