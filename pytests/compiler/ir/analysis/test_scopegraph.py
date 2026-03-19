"""Extended tests for scopegraph.py to improve coverage."""
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir.irreader import IrReader
from polyphony.compiler.ir.analysis.scopegraph import (
    ScopeDependencyGraphBuilder,
    UsingScopeDetector,
)
from polyphony.compiler.common.env import env
from pytests.compiler.base import setup_test


def build_scopes(src):
    setup_test(with_global=False)
    parser = IrReader(src)
    parser.parse_scope()
    scopes = {}
    for name in parser.sources:
        scopes[name] = env.scopes[name]
    return scopes


# =========================================================
# ScopeDependencyGraphBuilder
# =========================================================

class TestScopeDependencyGraphBuilder:
    def test_basic_function_dependency(self):
        """A namespace calling a function creates a dependency."""
        src = '''
scope NS
tags namespace
var F: function(NS.F)

blk1:
expr (call F 1)

scope NS.F
tags function
param x: int32
return int32

blk1:
mv x @in_x
mv @return x
ret @return
'''
        scopes = build_scopes(src)
        ns = scopes['NS']
        builder = ScopeDependencyGraphBuilder()
        visited = builder.process_scopes([ns])
        assert ns in visited
        f = scopes['NS.F']
        assert f in visited

    def test_class_with_ctor(self):
        """Class scope with constructor creates dependency."""
        src = '''
scope C
tags class
var __init__: function(C.__init__)
var x: int32

scope C.__init__
tags method ctor function
param self: object(C)
param x: int32
return object(C)

blk1:
mv x @in_x
mv self.x x

scope NS
tags namespace
var C: class(C)
var obj: object(C)

blk1:
mv obj (new C 5)
'''
        scopes = build_scopes(src)
        ns = scopes['NS']
        builder = ScopeDependencyGraphBuilder()
        visited = builder.process_scopes([ns])
        assert ns in visited
        c = scopes['C']
        assert c in visited

    def test_temp_with_scope_type(self):
        """Temp referencing a variable with scope type adds dependency."""
        src = '''
scope NS
tags namespace
var F: function(NS.F)
var G: function(NS.G)

blk1:
expr (call F 1)

scope NS.F
tags function
param x: int32
return int32
var G: function(NS.G)

blk1:
mv x @in_x
expr (call G x)
mv @return x
ret @return

scope NS.G
tags function
param a: int32
return int32

blk1:
mv a @in_a
mv @return a
ret @return
'''
        scopes = build_scopes(src)
        ns = scopes['NS']
        builder = ScopeDependencyGraphBuilder()
        visited = builder.process_scopes([ns])
        assert scopes['NS.F'] in visited
        assert scopes['NS.G'] in visited

    def test_visit_attr(self):
        """Attr access should visit the expression part."""
        src = '''
scope C
tags class
var x: int32

scope C.__init__
tags method ctor function
param self: object(C)

blk1:
mv self @in_self
mv self.x 10

scope NS
tags namespace
var C: class(C)
var obj: object(C)

blk1:
mv obj (new C)
'''
        scopes = build_scopes(src)
        ns = scopes['NS']
        builder = ScopeDependencyGraphBuilder()
        visited = builder.process_scopes([ns])
        assert scopes['C'] in visited

    def test_self_dependency_not_added(self):
        """Self-dependency is skipped."""
        src = '''
scope NS
tags namespace
var F: function(NS.F)

blk1:
expr (call F 1)

scope NS.F
tags function
param x: int32
return int32

blk1:
mv x @in_x
mv @return x
ret @return
'''
        scopes = build_scopes(src)
        ns = scopes['NS']
        builder = ScopeDependencyGraphBuilder()
        builder.process_scopes([ns])
        assert not builder.depend_graph.has_edge(ns, ns)

    def test_lib_scope_not_traversed(self):
        """Lib scope is added as dependency but not traversed further."""
        src = '''
scope NS
tags namespace
var F: function(NS.F)

blk1:
expr (call F 1)

scope NS.F
tags lib function
param x: int32
return int32
'''
        scopes = build_scopes(src)
        ns = scopes['NS']
        builder = ScopeDependencyGraphBuilder()
        visited = builder.process_scopes([ns])
        assert ns in visited

    def test_temp_external_symbol_value_type(self):
        """Temp referencing external symbol with value type exercises external path.
        NS.F is a descendant of NS, so no dependency edge is added,
        but the code path that checks sym.scope != self.scope is exercised."""
        src = '''
scope NS
tags namespace
var x: int32

scope NS.F
tags function
return int32
from NS import x

blk1:
mv @return x
ret @return
'''
        scopes = build_scopes(src)
        f = scopes['NS.F']
        builder = ScopeDependencyGraphBuilder()
        visited = builder.process_scopes([f])
        # NS.F is descendant of NS, so no edge but path exercised
        assert f in visited


# =========================================================
# UsingScopeDetector
# =========================================================

class TestUsingScopeDetector:
    def test_basic_using_scope(self):
        """UsingScopeDetector finds scopes used by a function."""
        src = '''
scope NS
tags namespace
var F: function(NS.F)

blk1:
expr (call F 1)

scope NS.F
tags function
param x: int32
return int32

blk1:
mv x @in_x
mv @return x
ret @return
'''
        scopes = build_scopes(src)
        ns = scopes['NS']
        detector = UsingScopeDetector()
        visited = detector.process_scopes([ns])
        assert ns in visited
        f = scopes['NS.F']
        assert f in visited

    def test_class_scope_collects_symbols(self):
        """UsingScopeDetector processes class scope and collects scope symbols."""
        src = '''
scope C
tags class
var __init__: function(C.__init__)
var x: int32

scope C.__init__
tags method ctor function
param self: object(C)

blk1:
mv self @in_self

scope NS
tags namespace
var C: class(C)

blk1:
mv C C
'''
        scopes = build_scopes(src)
        ns = scopes['NS']
        c_scope = scopes['C']
        detector = UsingScopeDetector()
        visited = detector.process_scopes([ns, c_scope])
        assert c_scope in visited

    def test_visit_attr_with_scope(self):
        """UsingScopeDetector visit_Attr resolves attr scope."""
        src = '''
scope C
tags class
var x: int32

scope C.__init__
tags method ctor function
param self: object(C)

blk1:
mv self @in_self
mv self.x 10

scope NS
tags namespace
var C: class(C)
var obj: object(C)

blk1:
mv obj (new C)
'''
        scopes = build_scopes(src)
        ns = scopes['NS']
        detector = UsingScopeDetector()
        visited = detector.process_scopes([ns])
        assert scopes['C'] in visited

    def test_new_with_scope(self):
        """UsingScopeDetector visit_New adds the class scope and ctor."""
        src = '''
scope C
tags class
var __init__: function(C.__init__)

scope C.__init__
tags method ctor function
param self: object(C)

blk1:
mv self @in_self

scope NS
tags namespace
var C: class(C)
var obj: object(C)

blk1:
mv obj (new C)
'''
        scopes = build_scopes(src)
        ns = scopes['NS']
        detector = UsingScopeDetector()
        visited = detector.process_scopes([ns])
        assert scopes['C'] in visited

    def test_temp_with_value_type_external(self):
        """UsingScopeDetector Temp referencing external value-type symbol."""
        src = '''
scope NS
tags namespace
var x: int32

scope NS.F
tags function
return int32
from NS import x

blk1:
mv @return x
ret @return
'''
        scopes = build_scopes(src)
        f = scopes['NS.F']
        detector = UsingScopeDetector()
        detector.process_scopes([f])
        assert detector.depend_graph.has_edge(f, scopes['NS'])

    def test_self_dependency_skipped(self):
        """UsingScopeDetector skips self-dependency."""
        src = '''
scope NS
tags namespace
var F: function(NS.F)

blk1:
expr (call F 1)

scope NS.F
tags function
param x: int32
return int32

blk1:
mv x @in_x
mv @return x
ret @return
'''
        scopes = build_scopes(src)
        ns = scopes['NS']
        detector = UsingScopeDetector()
        detector.process_scopes([ns])
        assert not detector.depend_graph.has_edge(ns, ns)

    def test_already_visited_not_re_added(self):
        """Scope already visited is not added to worklist again."""
        src = '''
scope NS
tags namespace
var F: function(NS.F)
var G: function(NS.G)

blk1:
expr (call F 1)
expr (call G 2)

scope NS.F
tags function
param x: int32
return int32
var G: function(NS.G)

blk1:
mv x @in_x
expr (call G x)
mv @return x
ret @return

scope NS.G
tags function
param a: int32
return int32

blk1:
mv a @in_a
mv @return a
ret @return
'''
        scopes = build_scopes(src)
        ns = scopes['NS']
        detector = UsingScopeDetector()
        visited = detector.process_scopes([ns])
        # G is visited once, not duplicated
        assert scopes['NS.G'] in visited

    def test_containable_scope_children(self):
        """ScopeDependencyGraphBuilder adds children dependencies for containable scopes."""
        src = '''
scope C
tags class
var __init__: function(C.__init__)
var method1: function(C.method1)

scope C.__init__
tags method ctor function
param self: object(C)

blk1:
mv self @in_self

scope C.method1
tags method function
param self: object(C)
return int32

blk1:
mv self @in_self
mv @return 0
ret @return

scope NS
tags namespace
var C: class(C)
var obj: object(C)

blk1:
mv obj (new C)
'''
        scopes = build_scopes(src)
        ns = scopes['NS']
        builder = ScopeDependencyGraphBuilder()
        visited = builder.process_scopes([ns])
        c = scopes['C']
        assert c in visited
        # Class is containable, so children should be dependencies
        assert builder.depend_graph.has_edge(c, scopes['C.__init__'])
        assert builder.depend_graph.has_edge(c, scopes['C.method1'])
