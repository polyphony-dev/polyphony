from polyphony.compiler.common.env import env
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir.ir import name2var as _v
from polyphony.compiler.ir import ir as new
from polyphony.compiler.ir.irreader import IRReader as IRParser, ir_stm
from polyphony.compiler.ir.irwriter import IRWriter
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.scope import (
    Scope,
    FunctionScope,
    ClassScope,
    NamespaceScope,
    GlobalScope,
    FunctionParam,
    FunctionParams,
    SymbolTable,
    function2method,
)
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.loop import Region
from pytests.compiler.base import setup_test, install_builtins, make_block, MockScope
import pytest

_writer = IRWriter()

def _stm_text(stm):
    """Format a statement (old or new IR) to text for comparison."""
    return _writer.write_stm(stm)


def test_Scope_find_sym():
    setup_test()
    top = env.scopes['@top']
    scope0 = Scope.create(top, 'scope0', set())
    scope1 = Scope.create(scope0, 'scope1', set())

    global_var = top.add_sym('GLOBAL_VAR', set(), Type.int())
    scope0_v = scope0.add_sym('v', set(), Type.int())
    scope0_w = scope0.add_sym('w', set(), Type.int())
    scope1_v = scope1.add_sym('v', set(), Type.int())

    assert scope1.find_sym('GLOBAL_VAR') is global_var
    assert scope0.find_sym('GLOBAL_VAR') is global_var
    assert scope1.find_sym('v') is scope1_v
    assert scope1.find_sym('w') is scope0_w
    assert scope0.find_sym('v') is scope0_v


def test_Scope_find_owner_scope():
    setup_test()
    top = env.scopes['@top']
    scope0 = Scope.create(top, 'scope0', set())
    scope1 = Scope.create(scope0, 'scope1', set())

    gvar = top.add_sym('GLOBAL_VAR', set(), Type.int())
    v0 = scope0.add_sym('v', set(), Type.int())
    w0 = scope0.add_sym('w', set(), Type.int())
    v1 = scope1.add_sym('v', set(), Type.int())
    scope1.import_sym(gvar)

    assert top.find_owner_scope(gvar) is top
    assert scope0.find_owner_scope(gvar) is top
    assert scope1.find_owner_scope(gvar) is scope1

    assert scope0.find_owner_scope(v0) is scope0
    assert scope0.find_owner_scope(w0) is scope0
    assert scope0.find_owner_scope(v1) is None

    assert scope1.find_owner_scope(v0) is scope0
    assert scope1.find_owner_scope(w0) is scope0
    assert scope1.find_owner_scope(v1) is scope1



def test_clone_function():
    setup_test()
    block_src = """
    scope @top.f
    tags function
    param a:int32
    return int32
    var x: int32

    blk1:
    mv a @in_a
    mv x (call g a)
    j blk2

    blk2:
    mv @return x
    ret @return

    scope @top.g
    tags function
    param x:int32
    return int32

    blk1:
    mv x @in_x
    mv @return x
    ret @return
    """

    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    top.add_sym('f', tags=set(), typ=Type.function('@top.f'))
    top.add_sym('g', tags=set(), typ=Type.function('@top.g'))

    f = env.scopes['@top.f']
    prefix = 'cloned'
    postfix = 'cloned'

    f_ = f.clone(prefix, postfix)

    f_clone = env.scopes['@top.cloned_f_cloned']
    assert f_clone is f_
    assert f_clone.parent is top
    assert f_clone.is_function()
    assert f_clone.origin is f
    assert f_clone.orig_name == '@top.f'

    new_sym = top.find_sym('cloned_f_cloned')
    assert new_sym
    assert new_sym.typ.is_function()
    assert new_sym.typ.scope is f_clone

    f_clone_a = f_clone.find_sym('a')
    assert f_clone_a
    f_clone_x = f_clone.find_sym('x')
    assert f_clone_x
    f_clone_ret = f_clone.find_sym('@return')
    assert f_clone_ret

    f_a = f.find_sym('a')
    f_x = f.find_sym('x')
    f_ret = f.find_sym('@return')
    assert f_clone_a is not f_a
    assert f_clone_x is not f_x
    assert f_clone_ret is not f_ret

    gen = f_clone.traverse_blocks()
    blk1 = next(gen)
    blk2 = next(gen)
    with pytest.raises(StopIteration) as e:
        next(gen)
    assert blk1.scope is f_clone
    assert blk2.scope is f_clone
    assert _stm_text(blk1.stms[0]) == 'mv a @in_a'
    assert _stm_text(blk1.stms[1]) == 'mv x (call g a)'
    assert isinstance(blk1.stms[2], Jump)
    assert blk1.stms[2].target is blk2
    assert _stm_text(blk2.stms[0]) == 'mv @return x'
    assert _stm_text(blk2.stms[1]) == 'ret @return'

    # Mutating the clone should not affect the original
    blk1.stms[1] = new.Move(dst=new.Temp(name='x', ctx=new.Ctx.STORE), src=new.Call(func=new.Temp(name='g'), args=[('', new.Const(value=1))]), block=blk1)

    gen = f.traverse_blocks()
    blk1_orig = next(gen)
    assert _stm_text(blk1_orig.stms[1]) == 'mv x (call g a)'


def test_recursive_clone():
    setup_test()
    block_src = """
    scope @top.f
    tags function
    param a:int32
    return int32
    var g: function(@top.f.g)
    var x: int32

    blk1:
    mv a @in_a
    mv x (call g a)
    j blk2

    blk2:
    mv @return x
    ret @return

    scope @top.f.g
    tags function
    param x:int32
    return int32

    blk1:
    mv x @in_x
    mv @return x
    ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    top.add_sym('f', tags=set(), typ=Type.function('@top.f'))

    f = env.scopes['@top.f']
    g = env.scopes['@top.f.g']
    prefix = 'cloned'
    postfix = 'cloned'
    f_ = f.clone(prefix, postfix, parent=f.parent, recursive=True)

    f_clone = env.scopes['@top.cloned_f_cloned']
    g_clone = env.scopes['@top.cloned_f_cloned.cloned_g_cloned']
    assert g_clone is not g
    assert g_clone.parent is f_clone
    assert g_clone.is_function()
    assert g_clone.origin is g
    assert g_clone.orig_name == '@top.f.g'

    new_g_sym = f_clone.find_sym('cloned_g_cloned')
    assert new_g_sym
    assert new_g_sym.typ.is_function()
    assert new_g_sym.typ.scope is g_clone

    assert f_clone.find_sym('g') is None

    gen = f_clone.traverse_blocks()
    blk1 = next(gen)
    blk2 = next(gen)
    assert _stm_text(blk1.stms[0]) == 'mv a @in_a'
    assert _stm_text(blk1.stms[1]) == 'mv x (call cloned_g_cloned a)'
    assert isinstance(blk1.stms[2], Jump)
    assert blk1.stms[2].target is blk2

    assert _stm_text(blk2.stms[0]) == 'mv @return x'
    assert _stm_text(blk2.stms[1]) == 'ret @return'

def test_legb():
    setup_test(with_global=False)
    block_src = """
    scope @top
    tags namespace
    var C: class(@top.C)
    var x: int32

    scope @top.C
    tags class
    var __init__: function(@top.C.__init__)
    var x: int16

    scope @top.C.__init__
    tags method
    """

    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    install_builtins(top)

    gx = top.find_sym('x')
    assert gx
    assert gx.typ.is_int()
    assert gx.typ.width == 32

    C = env.scopes['@top.C']
    assert C
    cx = C.find_sym('x')
    assert cx
    assert cx.typ.is_int()
    assert cx.typ.width == 16
    C_init = env.scopes['@top.C.__init__']
    assert C_init
    cix = C_init.find_sym('x')
    assert cix
    assert cix is gx
    assert cix is not cx


def test_instantiate_class():
    pass


# ============================================================
# FunctionParams tests
# ============================================================

class TestFunctionParams:
    def _make_params(self, is_method=False):
        setup_test()
        top = env.scopes["@top"]
        scope = Scope.create(top, "fp_scope", {"function"})
        fp = FunctionParams(is_method=is_method)
        return scope, fp

    def test_clear(self):
        """Cover line 68."""
        scope, fp = self._make_params()
        s1 = scope.add_sym("a", {"param"}, Type.int())
        fp.add_param(s1, None)
        assert len(fp) == 1
        fp.clear()
        assert len(fp) == 0

    def test_remove_by_sym(self):
        """Cover lines 71-78 (remove by Symbol object)."""
        scope, fp = self._make_params()
        s1 = scope.add_sym("@in_x", {"param"}, Type.int())
        s2 = scope.add_sym("@in_y", {"param"}, Type.int())
        fp.add_param(s1, None)
        fp.add_param(s2, None)
        fp.remove(s1)
        assert len(fp) == 1
        assert fp.symbols()[0] is s2

    def test_remove_by_name(self):
        """Cover line 75 (remove by param name string match)."""
        scope, fp = self._make_params()
        s1 = scope.add_sym("@in_x", {"param"}, Type.int())
        s2 = scope.add_sym("@in_y", {"param"}, Type.int())
        fp.add_param(s1, None)
        fp.add_param(s2, None)
        # remove by string name "x" which matches _param_name(s1)
        fp.remove("x")
        assert len(fp) == 1
        assert fp.symbols()[0] is s2

    def test_remove_by_indices_non_method(self):
        """Cover line 85 (remove_by_indices without method offset)."""
        scope, fp = self._make_params(is_method=False)
        s1 = scope.add_sym("@in_a", {"param"}, Type.int())
        s2 = scope.add_sym("@in_b", {"param"}, Type.int())
        s3 = scope.add_sym("@in_c", {"param"}, Type.int())
        fp.add_param(s1, None)
        fp.add_param(s2, None)
        fp.add_param(s3, None)
        fp.remove_by_indices([1])
        assert len(fp) == 2
        assert fp.symbols() == (s1, s3)

    def test_str_with_defval(self):
        """Cover lines 88-94 (__str__ with and without default values)."""
        scope, fp = self._make_params()
        s1 = scope.add_sym("@in_a", {"param"}, Type.int())
        s2 = scope.add_sym("@in_b", {"param"}, Type.int())
        fp.add_param(s1, None)
        fp.add_param(s2, Const(value=42))
        text = str(fp)
        assert "@in_a" in text
        assert "@in_b" in text
        assert "42" in text


# ============================================================
# SymbolTable tests
# ============================================================

class TestSymbolTable:
    def test_add_sym_duplicate_raises(self):
        """Cover line 116."""
        setup_test()
        top = env.scopes["@top"]
        scope = Scope.create(top, "st_scope", {"function"})
        scope.add_sym("x", set(), Type.int())
        with pytest.raises(RuntimeError, match="already registered"):
            scope.add_sym("x", set(), Type.int())

    def test_add_sym_none_type(self):
        """Cover line 114 (typ is None -> Type.undef())."""
        setup_test()
        top = env.scopes["@top"]
        scope = Scope.create(top, "st2", {"function"})
        sym = scope.add_sym("y", set(), None)
        assert sym.typ.is_undef()

    def test_import_sym_conflict_raises(self):
        """Cover line 146."""
        setup_test()
        top = env.scopes["@top"]
        scope = Scope.create(top, "imp_scope", {"function"})
        s1 = scope.add_sym("x", set(), Type.int())
        scope2 = Scope.create(top, "imp_scope2", {"function"})
        s2 = scope2.add_sym("x", set(), Type.int())
        # Import s2 with asname 'x' into scope where 'x' already exists as s1
        with pytest.raises(RuntimeError, match="already registered"):
            scope.import_sym(s2, "x")

    def test_find_sym_r_non_containable(self):
        """Cover line 166 (find_sym_r on non-containable type returns None)."""
        setup_test()
        top = env.scopes["@top"]
        scope = Scope.create(top, "fsr_scope", {"function"})
        scope.add_sym("x", set(), Type.int())
        result = scope.find_sym_r(["x", "something"])
        assert result is None

    def test_gen_sym_existing(self):
        """Cover line 181 (gen_sym when sym already exists)."""
        setup_test()
        top = env.scopes["@top"]
        scope = Scope.create(top, "gs_scope", {"function"})
        s1 = scope.add_sym("existing", set(), Type.int())
        s2 = scope.gen_sym("existing")
        assert s1 is s2

    def test_rename_sym_asname(self):
        """Cover lines 195-199."""
        setup_test()
        top = env.scopes["@top"]
        scope = Scope.create(top, "ren_scope", {"function"})
        s = scope.add_sym("old_name", set(), Type.int())
        result = scope.rename_sym_asname("old_name", "new_name")
        assert result is s
        assert "old_name" not in scope.symbols
        assert scope.symbols["new_name"] is s
        # Note: the symbol's name stays the same, only the key changes
        assert s.name == "old_name"

    def test_inherit_sym_imported(self):
        """Cover lines 204, 211 (inherit_sym with imported sym and ancestor)."""
        setup_test()
        top = env.scopes["@top"]
        scope = Scope.create(top, "inh_scope", {"function"})
        s = scope.add_sym("orig", set(), Type.int())
        ancestor_scope = Scope.create(top, "anc_scope", {"function"})
        anc_sym = ancestor_scope.add_sym("ancestor_sym", set(), Type.int())
        s.ancestor = anc_sym
        new_sym = scope.inherit_sym(s, "new_orig")
        assert new_sym.ancestor is anc_sym

    def test_free_symbols(self):
        """Cover line 225."""
        setup_test()
        top = env.scopes["@top"]
        scope = Scope.create(top, "free_scope", {"function"})
        s1 = scope.add_sym("a", set(), Type.int())
        s2 = scope.add_sym("b", {"free"}, Type.int())
        free = scope.free_symbols()
        assert s2 in free
        assert s1 not in free


# ============================================================
# Scope class tests
# ============================================================

class TestScopeCreate:
    def test_create_namespace_with_path(self):
        """Cover lines 299-301 (__file__ sym added when path given)."""
        setup_test()
        top = env.scopes["@top"]
        ns = Scope.create_namespace(top, "ns_with_path", set(), path="/some/path.py")
        filesym = ns.find_sym("__file__")
        assert filesym is not None
        assert ns.constants[filesym].value == "/some/path.py"

    def test_is_normal_scope(self):
        """Cover line 314."""
        setup_test()
        top = env.scopes["@top"]
        s = Scope.create(top, "normal_fn", {"function"})
        assert Scope.is_normal_scope(s) is True
        lib_fn = Scope.create(top, "lib_fn", {"lib", "function"})
        assert Scope.is_normal_scope(lib_fn) is False

    def test_get_scopes(self):
        """Cover lines 325-337."""
        setup_test()
        top = env.scopes["@top"]
        fn = Scope.create(top, "gs_fn", {"function"})
        cls = Scope.create(top, "gs_cls", {"class"})
        scopes_no_class = Scope.get_scopes(bottom_up=False, with_global=False, with_class=False)
        assert fn in scopes_no_class
        assert cls not in scopes_no_class
        scopes_with_class = Scope.get_scopes(bottom_up=False, with_global=False, with_class=True)
        assert cls in scopes_with_class

    def test_get_class_scopes(self):
        """Cover line 341."""
        setup_test()
        top = env.scopes["@top"]
        cls = Scope.create(top, "gc_cls", {"class"})
        class_scopes = Scope.get_class_scopes(bottom_up=False)
        assert cls in class_scopes

    def test_is_unremovable(self):
        """Cover line 349."""
        setup_test()
        top = env.scopes["@top"]
        s = Scope.create(top, "inst_scope", {"function", "instantiated"})
        assert Scope.is_unremovable(s) is True
        s2 = Scope.create(top, "not_inst", {"function"})
        assert Scope.is_unremovable(s2) is False


class TestScopeStr:
    def test_str_with_constants_and_params(self):
        """Cover lines 399-401, 404-407, 412 (__str__ branches)."""
        setup_test()
        top = env.scopes["@top"]
        scope = Scope.create(top, "str_scope", {"function"})
        sym = scope.add_sym("x", set(), Type.int())
        scope.constants[sym] = Const(value=10)
        psym = scope.add_sym("@in_a", {"param"}, Type.int())
        scope.function_params.add_param(psym, None)
        text = str(scope)
        assert "Constants:" in text
        assert "Parameters:" in text
        assert "None" in text  # return type is None

    def test_dump(self):
        """Cover line 427."""
        setup_test()
        top = env.scopes["@top"]
        scope = Scope.create(top, "dump_scope", {"function"})
        scope.dump()  # just ensure it runs

    def test_repr(self):
        """Cover line 430."""
        setup_test()
        top = env.scopes["@top"]
        scope = Scope.create(top, "repr_scope", {"function"})
        assert repr(scope) == scope.name

    def test_lt(self):
        """Cover line 433."""
        setup_test()
        top = env.scopes["@top"]
        s1 = Scope.create(top, "lt_a", {"function"})
        s2 = Scope.create(top, "lt_b", {"function"})
        assert (s1 < s2) == (s1.scope_id < s2.scope_id)


class TestMangledNames:
    def test_mangled_names_int(self):
        """Cover lines 439-463 (_mangled_names various type branches)."""
        setup_test()
        top = env.scopes["@top"]
        scope = Scope.create(top, "mn_scope", {"function"})
        result = scope._mangled_names([Type.int(32)])
        assert result == "i32"

    def test_mangled_names_bool(self):
        setup_test()
        top = env.scopes["@top"]
        scope = Scope.create(top, "mn_bool", {"function"})
        result = scope._mangled_names([Type.bool()])
        assert result == "b"

    def test_mangled_names_str(self):
        setup_test()
        top = env.scopes["@top"]
        scope = Scope.create(top, "mn_str", {"function"})
        result = scope._mangled_names([Type.str()])
        assert result == "s"

    def test_mangled_names_list(self):
        setup_test()
        top = env.scopes["@top"]
        scope = Scope.create(top, "mn_list", {"function"})
        result = scope._mangled_names([Type.list(Type.int(16), length=4)])
        assert "l_" in result

    def test_mangled_names_tuple(self):
        setup_test()
        top = env.scopes["@top"]
        scope = Scope.create(top, "mn_tuple", {"function"})
        result = scope._mangled_names([Type.tuple(Type.int(8), length=3)])
        assert "t_" in result

    def test_mangled_names_class(self):
        setup_test()
        top = env.scopes["@top"]
        cls_scope = Scope.create(top, "MyCls", {"class"})
        scope = Scope.create(top, "mn_class", {"function"})
        result = scope._mangled_names([Type.klass(cls_scope)])
        assert "c_MyCls" in result

    def test_mangled_names_object(self):
        setup_test()
        top = env.scopes["@top"]
        cls_scope = Scope.create(top, "MyObj", {"class"})
        scope = Scope.create(top, "mn_obj", {"function"})
        result = scope._mangled_names([Type.object(cls_scope)])
        assert "o_MyObj" in result

    def test_signature(self):
        """Cover lines 466-467."""
        setup_test()
        top = env.scopes["@top"]
        scope = Scope.create(top, "sig_scope", {"function"})
        psym = scope.add_sym("@in_a", {"param"}, Type.int(32))
        scope.function_params.add_param(psym, None)
        name, sig = scope.signature()
        assert name == scope.name
        assert "i32" in sig

    def test_unique_name(self):
        """Cover line 470."""
        setup_test()
        top = env.scopes["@top"]
        scope = Scope.create(top, "un_scope", {"function"})
        uname = scope.unique_name()
        assert "." not in uname


class TestScopeCloneSymbols:
    def test_clone_symbols_imported(self):
        """Cover lines 475-476 (clone_symbols_by_name with imported sym)."""
        setup_test()
        top = env.scopes["@top"]
        scope = Scope.create(top, "cs_src", {"function"})
        scope2 = Scope.create(top, "cs_dst", {"function"})
        ext_scope = Scope.create(top, "cs_ext", {"function"})
        ext_sym = ext_scope.add_sym("ext_var", set(), Type.int())
        scope.import_sym(ext_sym)
        scope.clone_symbols_by_name(scope2)
        assert "ext_var" in scope2.symbols
        assert scope2.symbols["ext_var"] is ext_sym


class TestScopeCloneBlocks:
    def test_clone_blocks_cjump(self):
        """Cover lines 499-500 (CJump block remapping)."""
        setup_test()
        block_src = """
        scope @top.cj_fn
        tags function
        var x: int32

        blk1:
        cj x blk2 blk3

        blk2:
        j blk3

        blk3:
        ret @return
        """
        IRParser(block_src).parse_scope()
        top = env.scopes["@top"]
        top.add_sym("cj_fn", tags=set(), typ=Type.function("@top.cj_fn"))
        scope = env.scopes["@top.cj_fn"]
        scope2 = Scope.create(top, "cj_fn2", {"function"})
        block_map, stm_map = scope.clone_blocks(scope2)
        # Verify CJump targets were remapped
        for stm in stm_map.values():
            if isinstance(stm, CJump):
                assert stm.true in block_map.values()
                assert stm.false in block_map.values()


class TestScopeFind:
    def test_find_child_recursive(self):
        """Cover lines 622-627 (find_child with rec=True)."""
        setup_test()
        top = env.scopes["@top"]
        parent = Scope.create(top, "fc_parent", {"function"})
        child = Scope.create(parent, "fc_child", {"function"})
        grandchild = Scope.create(child, "fc_grandchild", {"function"})
        # Find grandchild recursively from parent
        result = parent.find_child(grandchild.name, rec=True)
        assert result is not None
        found, p = result
        assert found is grandchild

    def test_find_child_not_recursive(self):
        """Cover line 630."""
        setup_test()
        top = env.scopes["@top"]
        parent = Scope.create(top, "fc2_parent", {"function"})
        child = Scope.create(parent, "fc2_child", {"function"})
        result = parent.find_child("fc2_child", rec=False)
        assert result is not None
        found, p = result
        assert found is child

    def test_find_parent_scope(self):
        """Cover lines 635, 637."""
        setup_test()
        top = env.scopes["@top"]
        parent = Scope.create(top, "fps_parent", {"function"})
        child = Scope.create(parent, "fps_child", {"function"})
        result = parent.find_parent_scope("fps_child")
        assert result is parent
        # Not found case
        result2 = child.find_parent_scope("nonexistent")
        assert result2 is None

    def test_find_scope(self):
        """Cover lines 642-650."""
        setup_test()
        top = env.scopes["@top"]
        parent = Scope.create(top, "fs_parent", {"function"})
        child = Scope.create(parent, "fs_child", {"function"})
        # Find self
        assert parent.find_scope("fs_parent") is parent
        # Find child
        assert parent.find_scope("fs_child") is child
        # Find via parent traversal
        assert child.find_scope("fs_parent") is parent
        # Not found at root
        assert top.find_scope("totally_nonexistent") is None

    def test_find_namespace(self):
        """Cover lines 653-656."""
        setup_test()
        top = env.scopes["@top"]
        fn = Scope.create(top, "fns_fn", {"function"})
        # top is a namespace
        assert fn.find_namespace() is top

    def test_find_param_sym(self):
        """Cover lines 695-696."""
        setup_test()
        top = env.scopes["@top"]
        scope = Scope.create(top, "fpsym_scope", {"function"})
        psym = scope.add_sym("@in_myp", {"param"}, Type.int())
        found = scope.find_param_sym("myp")
        assert found is psym

    def test_find_sym_builtin(self):
        """Cover line 715 (find_sym falls through to builtin_symbols)."""
        setup_test()
        top = env.scopes["@top"]
        # The global scope has no parent, so searching for a builtin name
        # should go to builtin_symbols
        from polyphony.compiler.ir.builtin import builtin_symbols
        if builtin_symbols:
            bname = next(iter(builtin_symbols))
            result = top.find_sym(bname)
            assert result is builtin_symbols[bname]

    def test_find_scope_sym_recursive(self):
        """Cover lines 720->723."""
        setup_test()
        top = env.scopes["@top"]
        parent = Scope.create(top, "fss_parent", {"function"})
        child = Scope.create(parent, "fss_child", {"function"})
        # Add a sym in child whose type references parent
        sym = child.add_sym("ref_sym", set(), Type.function(parent))
        results = parent.find_scope_sym(parent, rec=True)
        assert sym in results

    def test_qualified_name(self):
        """Cover lines 729-733."""
        setup_test()
        top = env.scopes["@top"]
        scope = Scope.create(top, "qn_scope", {"function"})
        qn = scope.qualified_name()
        assert "." not in qn or "_" in qn


class TestScopeRemoveParam:
    def test_remove_param_by_symbol(self):
        """Cover line 690."""
        setup_test()
        top = env.scopes["@top"]
        scope = Scope.create(top, "rp_scope", {"function"})
        s1 = scope.add_sym("@in_a", {"param"}, Type.int())
        scope.function_params.add_param(s1, None)
        scope.remove_param(s1)
        assert len(scope.function_params) == 0

    def test_clear_params(self):
        """Cover line 686."""
        setup_test()
        top = env.scopes["@top"]
        scope = Scope.create(top, "cp_scope", {"function"})
        s1 = scope.add_sym("@in_a", {"param"}, Type.int())
        scope.function_params.add_param(s1, None)
        scope.clear_params()
        assert len(scope.function_params) == 0


class TestScopeBlockOps:
    def test_traverse_blocks_empty(self):
        """Cover line 743->exit (no entry_block)."""
        setup_test()
        top = env.scopes["@top"]
        scope = Scope.create(top, "tb_scope", {"function"})
        blocks = list(scope.traverse_blocks())
        assert blocks == []

    def test_replace_block(self):
        """Cover lines 758-759."""
        setup_test()
        block_src = """
        scope @top.rb_fn
        tags function

        blk1:
        j blk2

        blk2:
        ret @return
        """
        IRParser(block_src).parse_scope()
        top = env.scopes["@top"]
        top.add_sym("rb_fn", tags=set(), typ=Type.function("@top.rb_fn"))
        scope = env.scopes["@top.rb_fn"]
        blocks = list(scope.traverse_blocks())
        old_blk = blocks[1]
        new_blk = Block(scope, "new_blk")
        scope.replace_block(old_blk, new_blk)
        # Check that predecessors now point to new block
        assert new_blk in blocks[0].succs or old_blk not in blocks[0].succs


class TestScopeChildren:
    def test_append_child_duplicate(self):
        """Cover line 762->exit (child already exists, no-op)."""
        setup_test()
        top = env.scopes["@top"]
        parent = Scope.create(top, "ac_parent", {"function"})
        child = Scope.create(parent, "ac_child", {"function"})
        count_before = len(parent.children)
        parent.append_child(child)  # duplicate, should not add
        assert len(parent.children) == count_before

    def test_collect_scope(self):
        """Cover line 772 (collect_scope)."""
        setup_test()
        top = env.scopes["@top"]
        parent = Scope.create(top, "col_parent", {"function"})
        child = Scope.create(parent, "col_child", {"function"})
        grandchild = Scope.create(child, "col_grandchild", {"function"})
        collected = parent.collect_scope()
        assert child in collected
        assert grandchild in collected

    def test_find_ctor(self):
        """Cover line 783."""
        setup_test()
        top = env.scopes["@top"]
        cls = Scope.create(top, "ctor_cls", {"class"})
        ctor = Scope.create(cls, "__init__", {"method", "ctor"})
        found = cls.find_ctor()
        assert found is ctor

    def test_find_ctor_none(self):
        """Cover line 783 (no ctor found)."""
        setup_test()
        top = env.scopes["@top"]
        cls = Scope.create(top, "no_ctor_cls", {"class"})
        assert cls.find_ctor() is None


class TestScopeSubclass:
    def test_is_subclassof(self):
        """Cover lines 793, 795-798."""
        setup_test()
        top = env.scopes["@top"]
        base = Scope.create(top, "base_cls", {"class"})
        derived = Scope.create(top, "derived_cls", {"class"})
        derived.bases = [base]
        assert derived.is_subclassof(base) is True
        assert derived.is_subclassof(derived) is True
        other = Scope.create(top, "other_cls", {"class"})
        assert derived.is_subclassof(other) is False

    def test_is_descendants_of(self):
        """Cover lines 811-815."""
        setup_test()
        top = env.scopes["@top"]
        parent = Scope.create(top, "desc_parent", {"function"})
        child = Scope.create(parent, "desc_child", {"function"})
        grandchild = Scope.create(child, "desc_grandchild", {"function"})
        assert grandchild.is_descendants_of(parent) is True
        assert child.is_descendants_of(parent) is True
        assert parent.is_descendants_of(child) is False

    def test_outer_module(self):
        """Cover lines 818-824."""
        setup_test()
        top = env.scopes["@top"]
        mod = Scope.create(top, "om_mod", {"function", "module"})
        child = Scope.create(mod, "om_child", {"function"})
        assert child.outer_module() is mod
        assert mod.outer_module() is mod
        # child directly under namespace
        fn = Scope.create(top, "om_fn", {"function"})
        assert fn.outer_module() is None

    def test_class_fields(self):
        """Cover lines 830-832."""
        setup_test()
        top = env.scopes["@top"]
        base = Scope.create(top, "cf_base", {"class"})
        base.add_sym("base_field", set(), Type.int())
        derived = Scope.create(top, "cf_derived", {"class"})
        derived.bases = [base]
        derived.add_sym("derived_field", set(), Type.int())
        fields = derived.class_fields()
        assert "base_field" in fields
        assert "derived_field" in fields


class TestScopeWorker:
    def test_register_worker(self):
        """Cover line 839."""
        setup_test()
        top = env.scopes["@top"]
        owner = Scope.create(top, "wk_owner", {"function"})
        worker = Scope.create(top, "wk_worker", {"function", "worker"})
        owner.register_worker(worker)
        assert worker in owner.workers
        assert worker.worker_owner is owner
        # Re-register same worker (cover dedup path)
        owner.register_worker(worker)
        assert owner.workers.count(worker) == 1


class TestScopeRegions:
    def _make_scope_with_blocks(self):
        setup_test()
        top = env.scopes["@top"]
        scope = Scope.create(top, "reg_scope", {"function"})
        blk1 = Block(scope, "blk1")
        blk2 = Block(scope, "blk2")
        blk3 = Block(scope, "blk3")
        return scope, blk1, blk2, blk3

    def test_region_operations(self):
        """Cover lines 874-877, 880-883, 892-898."""
        scope, blk1, blk2, blk3 = self._make_scope_with_blocks()
        r1 = Region(blk1, [blk2], [blk1, blk2])
        r2 = Region(blk3, [], [blk3])
        scope.set_top_region(r1)
        scope.append_child_regions(r1, [r2])
        # find_region
        found = scope.find_region(blk1)
        assert found is r1
        found2 = scope.find_region(blk3)
        assert found2 is r2
        # find_region for block not in any region
        blk4 = Block(scope, "blk4")
        assert scope.find_region(blk4) is None

    def test_remove_block_from_region(self):
        """Cover lines 880-883."""
        scope, blk1, blk2, blk3 = self._make_scope_with_blocks()
        r1 = Region(blk1, [blk2, blk3], [blk1, blk2, blk3])
        scope.set_top_region(r1)
        scope.remove_block_from_region(blk2)
        assert blk2 not in r1.bodies

    def test_remove_block_from_region_no_root(self):
        """Cover line 880 (early return when no root)."""
        scope, blk1, blk2, blk3 = self._make_scope_with_blocks()
        # No root set, should return without error
        scope.remove_block_from_region(blk1)

    def test_append_sibling_region(self):
        scope, blk1, blk2, blk3 = self._make_scope_with_blocks()
        r1 = Region(blk1, [blk2], [blk1, blk2])
        r2 = Region(blk3, [], [blk3])
        scope.set_top_region(r1)
        scope.append_child_regions(r1, [r2])
        blk5 = Block(scope, "blk5")
        r3 = Region(blk5, [], [blk5])
        scope.append_sibling_region(r2, r3)
        children = scope.child_regions(r1)
        assert r3 in children


class TestScopeBranchGraph:
    def test_add_branch_graph_edge(self):
        """Cover lines 892-898."""
        setup_test()
        top = env.scopes["@top"]
        scope = Scope.create(top, "bg_scope", {"function"})
        # Use integer stm ids (they need to be comparable with <)
        scope.add_branch_graph_edge(1, [[2, 3]])
        assert scope.has_branch_edge(1, 2) is True
        assert scope.has_branch_edge(2, 1) is True
        assert scope.has_branch_edge(1, 3) is True

    def test_has_branch_edge_reversed(self):
        """Cover lines 892-898 edge case where k > v."""
        setup_test()
        top = env.scopes["@top"]
        scope = Scope.create(top, "bg2_scope", {"function"})
        scope.add_branch_graph_edge(5, [[2]])
        assert scope.has_branch_edge(5, 2) is True
        assert scope.has_branch_edge(2, 5) is True


class TestScopeClosures:
    def test_closures(self):
        """Cover lines 909->911."""
        setup_test()
        top = env.scopes["@top"]
        parent = Scope.create(top, "clo_parent", {"function"})
        closure = Scope.create(parent, "clo_child", {"function", "closure"})
        non_closure = Scope.create(parent, "clo_normal", {"function"})
        nested_closure = Scope.create(non_closure, "clo_nested", {"function", "closure"})
        closures = parent.closures()
        assert closure in closures
        assert nested_closure in closures
        assert non_closure not in closures


class TestScopeInstanceNumber:
    def test_instance_number(self):
        """Cover line 926, 928."""
        setup_test()
        top = env.scopes["@top"]
        scope = Scope.create(top, "inum_scope", {"function"})
        n1 = scope.instance_number()
        n2 = scope.instance_number()
        assert n2 == n1 + 1


class TestFunction2Method:
    def test_function2method(self):
        """Cover lines 950-960."""
        setup_test()
        top = env.scopes["@top"]
        cls = Scope.create(top, "f2m_cls", {"class"})
        top.add_sym("f2m_cls", set(), Type.klass(cls))
        fn = Scope.create(cls, "my_method", {"function"})
        cls.add_sym("my_method", set(), Type.function(fn))
        psym = fn.add_sym("@in_x", {"param"}, Type.int())
        fn.function_params.add_param(psym, None)
        function2method(fn, cls)
        assert fn.is_method()
        assert not fn.is_function()
        # self should be the first param
        syms = fn.param_symbols(with_self=True)
        assert syms[0].name == "self"


class TestScopeIsAssignable:
    def test_is_assignable_via_origin(self):
        """Cover line 793 and is_assignable."""
        setup_test()
        top = env.scopes["@top"]
        s1 = Scope.create(top, "asg_s1", {"function"})
        s2 = Scope.create(top, "asg_s2", {"function"})
        s2.origin = s1
        assert s2.is_assignable(s1) is True
        s3 = Scope.create(top, "asg_s3", {"function"})
        s3.origin = s2
        assert s3.is_assignable(s1) is True


class TestScopeSetBoundArgs:
    def test_set_bound_args(self):
        """Cover line 932-933."""
        setup_test()
        top = env.scopes["@top"]
        scope = Scope.create(top, "ba_scope", {"class"})
        scope.set_bound_args([(0, Const(value=1)), (1, Const(value=2))])
        assert scope._bound_args == ["1", "2"]


class TestScopeSubclasses:
    def setup_method(self):
        setup_test()

    def test_create_function_scope(self):
        scope = Scope.create(
            env.scopes[env.global_scope_name], 'func', {'function'}, 1
        )
        assert isinstance(scope, FunctionScope)
        assert isinstance(scope, Scope)

    def test_create_method_scope(self):
        scope = Scope.create(
            env.scopes[env.global_scope_name], 'meth', {'method'}, 1
        )
        assert isinstance(scope, FunctionScope)

    def test_create_class_scope(self):
        scope = Scope.create(
            env.scopes[env.global_scope_name], 'Cls', {'class'}, 1
        )
        assert isinstance(scope, ClassScope)

    def test_create_namespace_scope(self):
        scope = Scope.create_namespace(
            None, 'pkg', {'namespace'}
        )
        assert isinstance(scope, NamespaceScope)

    def test_create_global_scope(self):
        gs = Scope.global_scope()
        assert isinstance(gs, GlobalScope)

    def test_isinstance_scope(self):
        scope = Scope.create(
            env.scopes[env.global_scope_name], 'f', {'function'}, 1
        )
        assert isinstance(scope, Scope)


class TestFunctionScopeFields:
    def setup_method(self):
        setup_test()

    def test_has_function_params(self):
        scope = Scope.create(
            env.scopes[env.global_scope_name], 'f', {'function'}, 1
        )
        assert hasattr(scope, 'function_params')
        assert isinstance(scope.function_params, FunctionParams)

    def test_has_return_type(self):
        scope = Scope.create(
            env.scopes[env.global_scope_name], 'f', {'function', 'returnable'}, 1
        )
        assert hasattr(scope, 'return_type')

    def test_has_loop_tree(self):
        scope = Scope.create(
            env.scopes[env.global_scope_name], 'f', {'function'}, 1
        )
        assert hasattr(scope, 'loop_tree')

    def test_namespace_no_function_params(self):
        scope = Scope.create_namespace(None, 'ns', {'namespace'})
        assert not hasattr(scope, 'function_params')
        assert not hasattr(scope, 'loop_tree')

    def test_class_no_function_params(self):
        scope = Scope.create(
            env.scopes[env.global_scope_name], 'C', {'class'}, 1
        )
        assert not hasattr(scope, 'function_params')

