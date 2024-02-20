import argparse
import json
import os
import sys
from collections import deque
from .driver import Driver

from .common.common import read_source
from .common.env import env
from .common.errors import CompileError, InterpretError

from .ahdl.hdlgen import HDLModuleBuilder
from .ahdl.hdlmodule import HDLScope, HDLModule
from .ahdl.stgbuilder import STGBuilder
from .ahdl.analysis.ahdlusedef import AHDLUseDefDetector
from .ahdl.transformers.ahdlopt import AHDLCopyOpt
from .ahdl.transformers.bitwidthreducer import BitwidthReducer
from .ahdl.transformers.canonical import Canonicalizer
from .ahdl.transformers.iotransformer import IOTransformer
from .ahdl.transformers.iotransformer import WaitTransformer
from .ahdl.transformers.statereducer import StateReducer

from .ir.builtin import builtin_symbols, clear_builtins
from .ir.scope import Scope
from .ir.symbol import Symbol
from .ir.setlineno import SourceDump
from .ir.synth import DefaultSynthParamSetter

from .ir.analysis.usedef import UseDefDetector
from .ir.analysis.fieldusedef import FieldUseDef
from .ir.analysis.diagnostic import CFGChecker
from .ir.analysis.loopdetector import LoopDetector
from .ir.analysis.loopdetector import LoopInfoSetter
from .ir.analysis.loopdetector import LoopRegionSetter
from .ir.analysis.loopdetector import LoopDependencyDetector
from .ir.analysis.regreducer import AliasVarDetector
from .ir.analysis.scopegraph import ScopeDependencyGraphBuilder
from .ir.analysis.scopegraph import UsingScopeDetector
from .ir.analysis.typecheck import TypeChecker
from .ir.analysis.typecheck import EarlyTypeChecker
from .ir.analysis.typecheck import PortAssignChecker
from .ir.analysis.typecheck import EarlyRestrictionChecker, RestrictionChecker, LateRestrictionChecker
from .ir.analysis.typecheck import AssertionChecker
from .ir.analysis.typecheck import SynthesisParamChecker

from .ir.transformers.bitwidth import TempVarWidthSetter
from .ir.transformers.cfgopt import BlockReducer, PathExpTracer
from .ir.transformers.cfgopt import HyperBlockBuilder
from .ir.transformers.constopt import ConstantOpt
from .ir.transformers.constopt import EarlyConstantOptNonSSA
from .ir.transformers.constopt import PolyadConstantFolding
from .ir.transformers.constopt import StaticConstOpt
from .ir.transformers.copyopt import CopyOpt, ObjCopyOpt
from .ir.transformers.deadcode import DeadCodeEliminator
from .ir.transformers.iftransform import IfTransformer, IfCondTransformer
from .ir.transformers.inlineopt import InlineOpt
from .ir.transformers.inlineopt import FlattenFieldAccess, FlattenObjectArgs, FlattenModule
from .ir.transformers.inlineopt import ObjectHierarchyCopier
from .ir.transformers.instantiator import ModuleInstantiator
from .ir.transformers.instantiator import find_called_module
from .ir.transformers.instantiator import ArgumentApplier
from .ir.transformers.looptransformer import LoopFlatten
from .ir.transformers.objtransform import ObjectTransformer
from .ir.transformers.phiopt import PHIInlining, LPHIRemover
from .ir.transformers.portconverter import PortTypeProp
from .ir.transformers.portconverter import FlippedTransformer
from .ir.transformers.portconverter import PortConnector
from .ir.transformers.quadruplet import EarlyQuadrupleMaker
from .ir.transformers.quadruplet import LateQuadrupleMaker
from .ir.transformers.ssa import ScalarSSATransformer
from .ir.transformers.ssa import TupleSSATransformer
from .ir.transformers.ssa import ListSSATransformer
from .ir.transformers.ssa import ObjectSSATransformer
from .ir.transformers.typeprop import TypePropagation
from .ir.transformers.typeprop import TypeSpecializer
from .ir.transformers.typeprop import StaticTypePropagation
from .ir.transformers.typeprop import TypeEvalVisitor
from .ir.transformers.unroll import LoopUnroller

from .ir.scheduling.dataflow import DFGBuilder
from .ir.scheduling.scheduler import Scheduler

from .frontend.python.irtranslator import IRTranslator
from .frontend.python.pure import interpret, PureCtorBuilder, PureFuncExecutor

from .target.verilog.vericodegen import VerilogCodeGen
from .target.verilog.veritestgen import VerilogTestGen
from .target.verilog.flatten import FlattenSignals

import logging
logger = logging.getLogger()

logging_setting = {
    'level': logging.DEBUG,
    'filename': '{}/debug_log'.format(env.debug_output_dir),
    'filemode': 'w'
}


def phase(phase):
    def setphase(driver):
        env.compile_phase = phase
    return setphase


def filter_scope(fn):
    def select_scope(driver):
        driver.set_filter(fn)
    select_scope.__name__ = f'filter_scope_{fn.__name__}'
    return select_scope


class ScopeSorter(object):
    def __init__(self):
        self._cached_scopes = []
        self._sorted_scopes = []
        self._scope_sort_keys: dict[Scope, tuple[int, int]] = {}

    def compare(self, scopes):
        if len(self._cached_scopes) != len(scopes):
            return False
        for s1, s2 in zip(self._cached_scopes, scopes):
            if s1 != s2:
                return False
        return True

    def update_cached_scopes(self, scopes):
        if self.compare(scopes):
            return False
        self._cached_scopes = scopes[:]
        return True

    def sort_scopes(self):
        graph_builder = ScopeDependencyGraphBuilder()
        graph_builder.process_scopes(self._cached_scopes)
        graph = graph_builder.depend_graph
        self._sorted_scopes = []
        order_map = graph.node_depth_map()
        self._sorted_scopes = sorted(self._cached_scopes, key=lambda s: (order_map[s], s.scope_id))

    def top_down(self, scopes):
        if self.update_cached_scopes(scopes):
            self.sort_scopes()
        return self._sorted_scopes[:]

    def bottom_up(self, scopes):
        if self.update_cached_scopes(scopes):
            self.sort_scopes()
        return list(reversed(self._sorted_scopes))


scope_sorter = ScopeSorter()


def set_scope_order(order_func):
    def f(driver):
        driver.set_order_func(order_func)
    f.__name__ = f'set_scope_order_{order_func.__name__}'
    return f


def bottom_up(scopes):
    return scope_sorter.bottom_up(scopes)


def top_down(scopes):
    return scope_sorter.top_down(scopes)


def is_static_scope(scope):
    return scope.is_namespace() or scope.is_class()


def is_not_static_scope(scope):
    return not is_static_scope(scope)


def is_inlined_module(scope):
    if scope.is_namespace():
        return False
    elif (scope.is_module()
        and scope.is_instantiated()
        and not scope.parent is Scope.global_scope()):
        return True
    elif is_inlined_module(scope.parent):
        return True
    return False


def is_uninlined_scope(scope):
    if is_static_scope(scope):
        return False
    if is_inlined_module(scope):
        return False
    return (scope.is_function_module()
            or scope.is_ctor() and scope.parent.is_module()
            or scope.is_worker()
            or scope.is_testbench()
            or scope.is_assigned()
            or scope.is_closure() and scope.parent and is_uninlined_scope(scope.parent)
            )


def is_hdlmodule_scope(scope):
    if is_inlined_module(scope):
        return False
    return HDLModule.is_hdlmodule_scope(scope)


def dump_source(driver):
    scopes = Scope.get_scopes(with_global=True, with_class=True)
    src_dump = SourceDump()
    for s in scopes:
        src_dump.process(s)


def select_using_scopes():
    def collect_scope_symbol(scope):
        scopes = []
        for sym in scope.symbols.values():
            if sym.typ.has_scope():
                s = sym.typ.scope
                if s.is_builtin() or s.is_decorator() or s.is_typeclass() or s.is_namespace():
                    continue
                scopes.append(s)
        return scopes

    top = Scope.global_scope()
    target_scopes = collect_scope_symbol(top)
    using_scopes = UsingScopeDetector().process_scopes([top] + target_scopes)
    return list(using_scopes)


def if_trans(driver, scope):
    IfTransformer().process(scope)


def ifcondtrans(driver, scope):
    IfCondTransformer().process(scope)


def reduce_blk(driver, scope):
    BlockReducer().process(scope)
    checkcfg(driver, scope)


def earlypathexp(driver, scope):
    LoopDetector().process(scope)
    PathExpTracer().process(scope)
    checkcfg(driver, scope)
    scope.reset_loop_tree()


def pathexp(driver, scope):
    PathExpTracer().process(scope)
    checkcfg(driver, scope)


def hyperblock(driver, scope):
    use_def(driver, scope)
    if not env.enable_hyperblock:
        return
    if scope.synth_params['scheduling'] == 'sequential':
        return
    HyperBlockBuilder().process(scope)
    checkcfg(driver, scope)
    reduce_blk(driver, scope)


def buildpurector(driver):
    new_ctors = PureCtorBuilder().process_all()
    for ctor in new_ctors:
        assert ctor.name in env.scopes
        driver.insert_scope(ctor)


def execpure(driver, scope):
    PureFuncExecutor().process(scope)


def execpureall(driver):
    PureFuncExecutor().process_all(driver)


def flipport(driver, scope):
    FlippedTransformer().process(scope)


def connectport(driver, scope):
    portconnector = PortConnector()
    portconnector.process(scope)
    for s in portconnector.scopes:
        driver.insert_scope(s)


def convport(driver):
    PortTypeProp().process_scopes(driver.current_scopes)


def early_quadruple(driver, scope):
    EarlyQuadrupleMaker().process(scope)


def late_quadruple(driver, scope):
    LateQuadrupleMaker().process(scope)


def use_def(driver, scope):
    UseDefDetector().process(scope)

def field_use_def(driver):
    modules = set()
    for s in driver.current_scopes:
        if s.is_module():
            modules.add(s)
        elif s.parent and s.parent.is_module():
            modules.add(s.parent)
    for module in modules:
        field_use_def = FieldUseDef()
        field_use_def.process(module)


def scalarssa(driver, scope):
    use_def(driver, scope)
    ScalarSSATransformer().process(scope)


def removelphi(driver, scope):
    LPHIRemover().process(scope)


def eval_type(driver, scope):
    TypeEvalVisitor().process(scope)


def early_static_type_prop(driver):
    StaticTypePropagation(is_strict=False).process_scopes(driver.current_scopes)
    typed_scopes = TypeSpecializer().process_scopes(driver.current_scopes)
    scopes = driver.all_scopes()
    for s in typed_scopes:
        if s not in scopes:
            driver.insert_scope(s)


def early_type_prop(driver):
    typed_scopes = TypeSpecializer().process_all()
    scopes = driver.all_scopes()
    for s in typed_scopes:
        if s not in scopes:
            driver.insert_scope(s)
    for s in scopes:
        if s in typed_scopes:
            continue
        if s.is_namespace():
            continue
        driver.remove_scope(s)


def type_prop(driver):
    typed_scopes = TypePropagation(is_strict=False).process_all()
    scopes = driver.all_scopes()
    for s in typed_scopes:
        if s not in scopes:
            driver.insert_scope(s)
    for s in scopes:
        if s in typed_scopes:
            continue
        if s.is_namespace():
            continue
        driver.remove_scope(s)


def static_type_prop(driver):
    StaticTypePropagation(is_strict=True).process_scopes(driver.current_scopes)


def strict_type_prop(driver):
    TypePropagation(is_strict=True).process_all()


def type_check(driver, scope):
    TypeChecker().process(scope)


def earlytypecheck(driver, scope):
    EarlyTypeChecker().process(scope)


def assigncheck(driver, scope):
    PortAssignChecker().process(scope)


def earlyrestrictioncheck(driver, scope):
    EarlyRestrictionChecker().process(scope)


def restriction_check(driver, scope):
    RestrictionChecker().process(scope)


def laterestrictioncheck(driver, scope):
    LateRestrictionChecker().process(scope)


def assertioncheck(driver, scope):
    AssertionChecker().process(scope)


def synthcheck(driver, scope):
    LoopDetector().process(scope)
    SynthesisParamChecker().process(scope)
    scope.reset_loop_tree()

def detectrom(driver):
    #RomDetector().process_all()
    pass


def instantiate(driver):
    modules = find_called_module([Scope.global_scope()])
    names = [''] * len(modules)  # work around
    for module, _ in modules:
        module.add_tag('top_module')
    while True:
        new_modules = ModuleInstantiator().process_modules(modules, names)
        if not new_modules:
            break
        orig_scopes = set()
        for module in new_modules:
            assert module.name in env.scopes
            assert module.is_module()
            driver.insert_scope(module)
            orig_scopes.add(module.origin)

            for s in module.collect_scope():
                if not s.is_instantiated():
                    continue
                driver.insert_scope(s)
                orig_scopes.add(s.origin)
        for s in orig_scopes:
            driver.remove_scope(s)
        scopes = [module.find_ctor() for module in new_modules]
        modules = find_called_module(scopes)


def apply_argument(driver):
    ArgumentApplier().process_all()


def inline_opt(driver):
    scopes = InlineOpt().process_scopes(driver.current_scopes)
    for s in scopes:
        assert s.name in env.scopes
        driver.insert_scope(s)


def setsynthparams(driver, scope):
    DefaultSynthParamSetter().process(scope)


def flattenmodule(driver, scope):
    scopes = FlattenModule().process(scope)
    for s in scopes:
        driver.insert_scope(s)


def objssa(driver, scope):
    use_def(driver, scope)
    TupleSSATransformer().process(scope)
    early_quadruple(driver, scope)
    use_def(driver, scope)
    ListSSATransformer().process(scope)
    ObjectHierarchyCopier().process(scope)
    use_def(driver, scope)
    ObjectSSATransformer().process(scope)


def objcopyopt(driver, scope):
    use_def(driver, scope)
    ObjCopyOpt().process(scope)


def objtrans(driver, scope):
    use_def(driver, scope)
    ObjectTransformer().process(scope)


def scalarize(driver, scope):
    #FlattenObjectArgs().process(scope)
    #dumpscope(driver, scope)
    FlattenFieldAccess().process(scope)
    #dumpscope(driver, scope)
    checkcfg(driver, scope)


def static_const_opt(driver):
    for s in driver.current_scopes:
        UseDefDetector().process(s)
    StaticConstOpt().process_scopes(driver.current_scopes)


def earlyconstopt_nonssa(driver, scope):
    use_def(driver, scope)
    EarlyConstantOptNonSSA().process(scope)
    checkcfg(driver, scope)


def constopt(driver, scope):
    use_def(driver, scope)
    ConstantOpt().process(scope)


def copyopt(driver, scope):
    use_def(driver, scope)
    CopyOpt().process(scope)


def phiopt(dfiver, scope):
    PHIInlining().process(scope)


def checkcfg(driver, scope):
    if env.dev_debug_mode:
        CFGChecker().process(scope)


def loop(driver, scope):
    use_def(driver, scope)
    LoopDetector().process(scope)
    #LoopRegionSetter().process(scope)
    LoopInfoSetter().process(scope)
    LoopDependencyDetector().process(scope)
    checkcfg(driver, scope)


def looptrans(driver, scope):
    if LoopFlatten().process(scope):
        hyperblock(driver, scope)
        loop(driver, scope)
        reduce_blk(driver, scope)


def unroll(driver, scope):
    while LoopUnroller().process(scope):
        dumpscope(driver, scope)
        use_def(driver, scope)
        checkcfg(driver, scope)
        reduce_blk(driver, scope)
        PolyadConstantFolding().process(scope)
        pathexp(driver, scope)
        dumpscope(driver, scope)
        constopt(driver, scope)
        copyopt(driver, scope)
        deadcode(driver, scope)
        LoopInfoSetter().process(scope)
        LoopRegionSetter().process(scope)
        LoopDependencyDetector().process(scope)


def deadcode(driver, scope):
    use_def(driver, scope)
    DeadCodeEliminator().process(scope)


def aliasvar(driver, scope):
    use_def(driver, scope)
    AliasVarDetector().process(scope)


def tempbit(driver, scope):
    TempVarWidthSetter().process(scope)


def dfg(driver, scope):
    use_def(driver, scope)
    DFGBuilder().process(scope)


def schedule(driver, scope):
    Scheduler().schedule(scope)


def createhdlscope(driver):
    scopes = deque(driver.all_scopes())
    visited = set()
    while scopes:
        scope = scopes.popleft()
        if scope in visited:
            continue
        if not HDLModule.is_hdlmodule_scope(scope) and not is_static_scope(scope):
            continue
        if scope.parent:
            scopes.append(scope.parent)
        if HDLModule.is_hdlmodule_scope(scope):
            hdl = HDLModule(scope, scope.base_name, scope.qualified_name())
        else:
            hdl = HDLScope(scope, scope.base_name, scope.qualified_name())
        env.append_hdlscope(hdl)
        visited.add(scope)
        if scope.is_instantiated():
            for b in scope.bases:
                if env.hdlscope(b) is None:
                    basemodule = HDLModule(b, b.base_name, b.qualified_name())
                    env.append_hdlscope(basemodule)


def stg(driver, scope):
    hdlmodule = env.hdlscope(scope)
    STGBuilder().process(hdlmodule)


def reducestate(driver, scope):
    hdlmodule = env.hdlscope(scope)
    StateReducer().process(hdlmodule)


def transformio(driver, scope):
    hdlmodule = env.hdlscope(scope)
    IOTransformer().process(hdlmodule)


def transformwait(driver, scope):
    hdlmodule = env.hdlscope(scope)
    WaitTransformer().process(hdlmodule)


def reducereg(driver, scope):
    pass


def ahdlcopyopt(driver, scope):
    hdlmodule = env.hdlscope(scope)
    AHDLCopyOpt().process(hdlmodule)


def reducebits(driver, scope):
    hdlmodule = env.hdlscope(scope)
    BitwidthReducer().process(hdlmodule)


def buildmodule(driver, scope):
    hdlmodule = env.hdlscope(scope)
    modulebuilder = HDLModuleBuilder.create(hdlmodule)
    assert modulebuilder
    modulebuilder.process(hdlmodule)


def ahdluse_def(driver, scope):
    hdlmodule = env.hdlscope(scope)
    AHDLUseDefDetector().process(hdlmodule)


def canonicalize(driver, scope):
    hdlmodule = env.hdlscope(scope)
    Canonicalizer().process(hdlmodule)


def dumpscope(driver, scope):
    driver.logger.debug(str(scope))


def printscopename(driver, scope):
    print(scope.name)


def dumpcfgimg(driver, scope):
    from .ir.scope import write_dot
    if scope.is_function() or scope.is_function_module() or scope.is_method() or scope.is_module():
        write_dot(scope, f'{driver.stage - 1}_{driver.procs[driver.stage - 1].__name__}')


def dumpdfgimg(driver, scope):
    if scope.is_function_module() or scope.is_method() or scope.is_module():
        for dfg in scope.dfgs():
            dfg.write_dot(f'{scope.base_name}_{dfg.name}')


def dumpdependimg(driver):
    env.depend_graph.write_dot(f'depend_graph_{driver.stage}')


def dumpdfg(driver, scope):
    for dfg in scope.dfgs():
        driver.logger.debug(str(dfg))


def dumpsched(driver, scope):
    for dfg in scope.dfgs():
        driver.logger.debug('--- ' + dfg.name)
        for n in dfg.get_scheduled_nodes():
            driver.logger.debug(n)


def dumpstg(driver, scope):
    hdlmodule = env.hdlscope(scope)
    for fsm in hdlmodule.fsms.values():
        for stg in fsm.stgs:
            driver.logger.debug(str(stg))


def dumpmodule(driver, scope):
    hdlmodule = env.hdlscope(scope)
    logger.debug(str(hdlmodule))


def dumphdl(driver, scope):
    logger.debug(driver.result(scope))


def printresouces(driver, scope):
    hdlmodule = env.hdlscope(scope)
    if (scope.is_function_module() or scope.is_module()):
        resources = hdlmodule.resources()
        print(resources)


def compile_plan():
    def dbg(proc):
        return proc if env.dev_debug_mode else None

    def ahdlopt(proc):
        return proc if env.enable_ahdl_opt else None

    def pure(proc):
        return proc if env.config.enable_pure else None

    plan = [
        if_trans,
        reduce_blk,
        early_quadruple,
        early_type_prop,

        set_scope_order(bottom_up),

        filter_scope(is_static_scope),
        late_quadruple,

        earlyrestrictioncheck,
        use_def,
        static_const_opt,
        eval_type,

        static_type_prop,

        type_check,
        restriction_check,
        use_def,

        filter_scope(is_not_static_scope),

        # flipport,
        connectport,
        type_prop,

        assigncheck,
        late_quadruple,
        ifcondtrans,

        earlyrestrictioncheck,
        earlytypecheck,
        type_prop,
        restriction_check,

        earlyconstopt_nonssa,
        instantiate,
        type_prop,

        phase(env.PHASE_1),

        synthcheck,
        inline_opt,

        filter_scope(is_uninlined_scope),
        flattenmodule,

        setsynthparams,
        reduce_blk,
        earlypathexp,
        phase(env.PHASE_2),
        # TODO: Enable/disable flatten
        # flattenmodule,

        objssa,
        objcopyopt,
        objtrans,
        scalarize,

        scalarssa,
        hyperblock,
        reduce_blk,
        type_prop,
        copyopt,
        phiopt,
        constopt,
        deadcode,

        phase(env.PHASE_3),
        eval_type,
        strict_type_prop,
        type_check,

        apply_argument,
        copyopt,
        constopt,
        deadcode,

        reduce_blk,
        loop,
        looptrans,
        laterestrictioncheck,
        unroll,
        pathexp,
        removelphi,

        phase(env.PHASE_4),
        convport,

        phase(env.PHASE_5),
        field_use_def,
        aliasvar,
        tempbit,
        dfg,
        dbg(dumpdfg),
        schedule,
        dbg(dumpsched),
        assertioncheck,

        createhdlscope,
        filter_scope(is_hdlmodule_scope),
        stg,
        dbg(dumpstg),
        buildmodule,
        dbg(dumpmodule),
        ahdlopt(ahdlcopyopt),
        #ahdlopt(reducebits),
        #ahdlopt(reducereg),
        dbg(dumpmodule),
        transformio,
        dbg(dumpmodule),
        reducestate,
        dbg(dumpmodule),
        transformwait,
        dbg(dumpmodule),
        #reducestate,
        #dbg(dumpmodule),
        canonicalize,
    ]
    plan = [p for p in plan if p is not None]
    return plan


def initialize():
    env.__init__()
    Symbol.initialize()
    clear_builtins()


def setup(src_file, options):
    initialize()
    setup_options(options)
    setup_builtins()
    setup_global(src_file)


def setup_options(options):
    env.dev_debug_mode = options.debug_mode
    env.verbose_level = options.verbose_level if options.verbose_level else 0
    env.quiet_level = options.quiet_level if options.quiet_level else 0
    env.enable_verilog_dump = options.verilog_dump
    env.enable_verilog_monitor = options.verilog_monitor
    env.targets = options.targets
    if options.config:
        try:
            if os.path.exists(options.config):
                with open(options.config, 'r') as f:
                    config = json.load(f)
            else:
                config = json.loads(options.config)
            env.load_config(config)
        except:
            print('invalid config option', options.config)
    if env.dev_debug_mode:
        logging.basicConfig(**logging_setting)


def setup_builtins():
    translator = IRTranslator()
    root_dir = '{0}{1}{2}{1}'.format(
        os.path.dirname(__file__),
        os.path.sep, os.path.pardir
    )
    env.root_dir = os.path.abspath(root_dir)
    internal_dir = f'{env.root_dir}{os.path.sep}_internal'
    builtin_package_file = f'{internal_dir}{os.sep}_builtins.py'
    env.set_current_filename(builtin_package_file)
    translator.translate(read_source(builtin_package_file), '__builtin__')


def setup_global(src_file):
    env.set_current_filename(src_file)
    g = Scope.create_namespace(None, env.global_scope_name, {'global'}, src_file)
    env.push_outermost_scope(g)
    for sym in builtin_symbols.values():
        g.import_sym(sym)


# replace a target scope name to a scope object
def parse_targets(scopes):
    if not env.targets:
        raise RuntimeError('compile targets not found')
    scope_dict = {s.name: s for s in scopes}
    for i, (name, args_str) in enumerate(env.targets):
        scope_name = f'{env.global_scope_name}.{name}'
        if scope_name in scope_dict:
            target_scope = scope_dict[scope_name]
            args = []
            for a in args_str:
                if a.isdigit() or a[0] == '-' and a[1:].isdigit():
                    args.append(int(a))
                elif a[0] == ':':
                    # a as a type name
                    a_scope = Scope.global_scope().find_scope(a)
                    if not a_scope:
                        raise RuntimeError(f'{a} not found')
                    args.append(a_scope)
                else:
                    args.append(a)
            env.targets[i] = (target_scope, args)
        else:
            raise RuntimeError(f'{name} not found')


def compile(plan, source, src_file=''):
    translator = IRTranslator()
    translator.translate(source, '')
    if env.config.enable_pure:
        interpret(source, src_file)
    using_scopes = select_using_scopes()
    driver = Driver(plan, using_scopes, None)
    driver.run('Compiling scopes')
    return driver.current_scopes


def compile_main(src_file, options):
    setup(src_file, options)
    main_source = read_source(src_file)
    plan = compile_plan()
    scopes = compile(plan, main_source, src_file)
    output_hdl(output_plan(), scopes, options, stage_offset=len(plan))
    env.destroy()


def output_plan():
    plan = [
        filter_scope(is_hdlmodule_scope),
        dumpmodule,
        # TODO: Enable/disable flatten
        ahdl_flatten_signals,
        dumpmodule,
        output_verilog,
    ]
    return plan


def output_hdl(plan, compiled_scopes, options, stage_offset):
    driver = Driver(plan, compiled_scopes, options, stage_offset)
    driver.run('Output HDL')


def ahdl_flatten_signals(driver, scope):
    hdlmodule = env.hdlscope(scope)
    FlattenSignals().process(hdlmodule)


def output_verilog(driver):
    options = driver.options
    results = []
    for s in driver.current_scopes:
        hdlmodule = env.hdlscope(s)
        code = genhdl(hdlmodule)
        if options.debug_mode:
            logger.debug(code)
            if s.is_function_module() or s.is_module():
                resources = hdlmodule.resources()
                print(resources)
        results.append((s, hdlmodule, code))

    output_name = options.output_name
    d = options.output_dir if options.output_dir else './'
    if d[-1] != '/':
        d += '/'

    if output_name.endswith('.v'):
        output_name = output_name[:-2]
    output_file_name = output_name + '.v'
    with open(d + output_file_name, 'w') as f:
        for scope, _, code in results:
            scope_name = scope.qualified_name()
            if options.output_prefix:
                file_name = f'{options.output_prefix}_{scope_name}.v'
            else:
                file_name = f'{scope_name}.v'
            if output_file_name == file_name:
                file_name = '_' + file_name
            with open('{}{}'.format(d, file_name), 'w') as f2:
                f2.write(code)
            if scope.is_testbench():
                env.append_testbench(scope)
            else:
                f.write('`include "./{}"\n'.format(file_name))


def genhdl(hdlmodule):
    if not hdlmodule.scope.is_testbench():
        vcodegen = VerilogCodeGen(hdlmodule)
    else:
        vcodegen = VerilogTestGen(hdlmodule)
    vcodegen.generate()
    return vcodegen.result()


def main():
    parser = argparse.ArgumentParser(prog='polyphony')

    parser.add_argument('-o', '--output', dest='output_name',
                        default='polyphony_out',
                        help='output filename (default is "polyphony_out")',
                        metavar='FILE')
    parser.add_argument('-d', '--dir', dest='output_dir',
                        metavar='DIR', help='output directory')
    parser.add_argument('-c', '--config', dest='config',
                        metavar='CONFIG', help='set configration(json literal or file)')
    parser.add_argument('-v', '--verbose', dest='verbose_level',
                        action='count', help='verbose output')
    parser.add_argument('-D', '--debug', dest='debug_mode',
                        action='store_true', help='enable debug mode')
    parser.add_argument('-q', '--quiet', dest='quiet_level',
                        action='count', help='suppress warning/error messages')
    parser.add_argument('-vd', '--verilog_dump', dest='verilog_dump',
                        action='store_true', help='output vcd file in testbench')
    parser.add_argument('-vm', '--verilog_monitor', dest='verilog_monitor',
                        action='store_true', help='enable $monitor in testbench')
    parser.add_argument('-op', '--output_prefix', metavar='PREFIX',
                        dest='output_prefix', help='output name prefix')
    from .. version import __version__
    parser.add_argument('-V', '--version', action='version',
                        version='%(prog)s ' + __version__,
                        help='print the Polyphony version number')
    parser.add_argument('source', help='Python source file')
    options = parser.parse_args()
    if not os.path.isfile(options.source):
        print(options.source + ' is not valid file name')
        parser.print_help()
        sys.exit(0)
    if options.verbose_level:
        logging.basicConfig(level=logging.INFO)

    try:
        compile_main(options.source, options)
    except CompileError as e:
        if options.debug_mode:
            raise
        print(e)
    except InterpretError as e:
        if options.debug_mode:
            raise
        print(e)
    except Exception as e:
        raise


if __name__ == "__main__":
    main()

