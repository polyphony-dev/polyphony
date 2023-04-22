import argparse
import json
import os
import sys

from .driver import Driver

from .common.common import read_source
from .common.env import env
from .common.errors import CompileError, InterpretError

from .ahdl.hdlgen import HDLModuleBuilder
from .ahdl.hdlmodule import HDLScope, HDLModule
from .ahdl.stg import STGBuilder
from .ahdl.analysis.ahdlusedef import AHDLUseDefDetector
from .ahdl.transformers.ahdlopt import AHDLCopyOpt
from .ahdl.transformers.bitwidthreducer import BitwidthReducer
from .ahdl.transformers.canonical import Canonicalizer
from .ahdl.transformers.iotransformer import IOTransformer
from .ahdl.transformers.iotransformer import WaitTransformer
from .ahdl.transformers.statereducer import StateReducer

from .ir.builtin import builtin_symbols
from .ir.scope import Scope
from .ir.symbol import Symbol
from .ir.setlineno import SourceDump
from .ir.synth import DefaultSynthParamSetter

from .ir.analysis.usedef import UseDefDetector
from .ir.analysis.usedef import FieldUseDef
from .ir.analysis.diagnostic import CFGChecker
from .ir.analysis.loopdetector import LoopDetector
from .ir.analysis.loopdetector import LoopInfoSetter
from .ir.analysis.loopdetector import LoopRegionSetter
from .ir.analysis.loopdetector import LoopDependencyDetector
from .ir.analysis.regreducer import AliasVarDetector
from .ir.analysis.scopegraph import CallGraphBuilder
from .ir.analysis.scopegraph import DependencyGraphBuilder
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
from .ir.transformers.inlineopt import SpecializeWorker
from .ir.transformers.instantiator import ModuleInstantiator
from .ir.transformers.looptransformer import LoopFlatten
from .ir.transformers.objtransform import ObjectTransformer
from .ir.transformers.phiopt import PHIInlining, LPHIRemover
from .ir.transformers.portconverter import PortConverter
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
from .ir.transformers.typeprop import InstanceTypePropagation
from .ir.transformers.typeprop import StaticTypePropagation
from .ir.transformers.typeprop import TypeEvalVisitor
from .ir.transformers.unroll import LoopUnroller

from .ir.scheduling.dataflow import DFGBuilder
from .ir.scheduling.scheduler import Scheduler

from .frontend.python.irtranslator import IRTranslator
from .frontend.python.pure import interpret, PureCtorBuilder, PureFuncExecutor

from .target.verilog.vericodegen import VerilogCodeGen
from .target.verilog.veritestgen import VerilogTestGen

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
        for s in driver.all_scopes():
            if fn(s):
                driver.enable_scope(s)
            else:
                driver.disable_scope(s)
    return select_scope


def is_static_scope(scope):
    return scope.is_namespace() or scope.is_class()


def is_not_static_scope(scope):
    return not is_static_scope(scope)


def is_uninlined_scope(scope):
    if is_static_scope(scope):
        return False
    if scope.is_ctor() and not scope.parent.is_module():
        return False
    return True


def is_synthesis_target_scope(scope):
    if scope.is_instantiated() or scope.is_function_module() or scope.is_testbench():
        return True
    if scope.parent and is_synthesis_target_scope(scope.parent):
        return True
    return False


def is_hdlmodule_scope(scope):
    return HDLModule.is_hdlmodule_scope(scope)


def is_hdl_scope(scope):
    if is_hdlmodule_scope(scope) or scope.is_interface() or scope.is_testbench() or scope.is_class() or scope.is_namespace():
        return True
    return False


def preprocess_global(driver):
    scopes = Scope.get_scopes(with_global=True, with_class=True)
    src_dump = SourceDump()
    for s in scopes:
        src_dump.process(s)


def scopegraph(driver):
    uncalled_scopes = CallGraphBuilder().process_all()
    using_scopes, unused_scopes = DependencyGraphBuilder().process_all()
    targets = {target for target, _ in env.targets}
    for s in uncalled_scopes:
        if s.is_namespace() or s.is_class() or s.is_worker():
            continue
        if s.is_ctor() and s.parent.is_module() and s.parent in driver.scopes:
            continue
        if s.is_instantiated():
            continue
        if s in targets or s.origin in targets:
            continue
        driver.remove_scope(s)
        Scope.destroy(s)
    for s in unused_scopes:
        if s.is_namespace():
            continue
        if s.is_builtin() and s.is_typeclass():
            continue
        if s.is_instantiated():
            continue
        if s.name in env.scopes:
            driver.remove_scope(s)
            Scope.destroy(s)


def iftrans(driver, scope):
    IfTransformer().process(scope)


def ifcondtrans(driver, scope):
    IfCondTransformer().process(scope)


def reduceblk(driver, scope):
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
    if not env.enable_hyperblock:
        return
    if scope.synth_params['scheduling'] == 'sequential':
        return
    HyperBlockBuilder().process(scope)
    checkcfg(driver, scope)


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
    PortConverter().process_all()
    #PortConverter().process(scope)


def earlyquadruple(driver, scope):
    EarlyQuadrupleMaker().process(scope)


def latequadruple(driver, scope):
    LateQuadrupleMaker().process(scope)


def usedef(driver, scope):
    UseDefDetector().process(scope)


def fieldusedef(driver):
    scopes = driver.get_scopes(with_global=False,
                               with_class=True,
                               with_lib=False)
    for s in scopes:
        if s.is_module():
            field_usedef = FieldUseDef()
            field_usedef.process(s, driver)


def scalarssa(driver, scope):
    ScalarSSATransformer().process(scope)


def removelphi(driver, scope):
    LPHIRemover().process(scope)


def evaltype(driver, scope):
    TypeEvalVisitor().process(scope)


def earlytypeprop(driver):
    def static_scope(s):
        if s.is_namespace():
            return True
        elif s.is_class():
            return True
        return False
    StaticTypePropagation(is_strict=False).process_all()
    typed_scopes = TypeSpecializer().process_all()
    scopes = driver.all_scopes()
    for s in typed_scopes:
        if s not in scopes:
            driver.insert_scope(s)
    for s in scopes:
        # The namespace scope should not be removed here,
        # since staticconstopt will be executed later
        if s not in typed_scopes and not static_scope(s):
            driver.remove_scope(s)


def typeprop(driver):
    TypePropagation().process_all()


def statictypeprop(driver):
    StaticTypePropagation(is_strict=True).process_all()


def stricttypeprop(driver):
    TypePropagation(is_strict=True).process_all()


def typecheck(driver, scope):
    TypeChecker().process(scope)


def earlytypecheck(driver, scope):
    EarlyTypeChecker().process(scope)


def assigncheck(driver, scope):
    PortAssignChecker().process(scope)


def earlyrestrictioncheck(driver, scope):
    EarlyRestrictionChecker().process(scope)


def restrictioncheck(driver, scope):
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

def specworker(driver, scope):
    new_workers = SpecializeWorker().process(scope)
    for w in new_workers:
        driver.insert_scope(w)


def instantiate(driver):
    new_modules = ModuleInstantiator().process_all()
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
            usedef(driver, s)
            constopt(driver, s)

    for s in orig_scopes:
        driver.remove_scope(s)

def postinstantiate(driver):
    scopes = driver.get_scopes(with_global=False,
                               with_class=True,
                               with_lib=False)
    scopes = [scope for scope in scopes if scope.is_instantiated()]
    if not scopes:
        return
    #for s in scopes:
    #    if env.config.enable_pure:
    #        execpure(driver, s)
    for s in scopes:
        constopt(driver, s)
        checkcfg(driver, s)
    TypePropagation().process_all()
    scopegraph(driver)
    detectrom(driver)
    for s in scopes:
        constopt(driver, s)


def inlineopt(driver):
    inlineopt = InlineOpt()
    inlineopt.process_all(driver)
    for s in inlineopt.new_scopes:
        assert s.name in env.scopes
        driver.insert_scope(s)
    scopegraph(driver)


def setsynthparams(driver, scope):
    DefaultSynthParamSetter().process(scope)


def flattenmodule(driver, scope):
    FlattenModule(driver).process(scope)


def objssa(driver, scope):
    TupleSSATransformer().process(scope)
    earlyquadruple(driver, scope)
    usedef(driver, scope)
    ListSSATransformer().process(scope)
    ObjectHierarchyCopier().process(scope)
    usedef(driver, scope)
    ObjectSSATransformer().process(scope)


def objcopyopt(driver, scope):
    usedef(driver, scope)
    ObjCopyOpt().process(scope)


def objtrans(driver, scope):
    ObjectTransformer().process(scope)


def scalarize(driver, scope):
    FlattenObjectArgs().process(scope)
    #dumpscope(driver, scope)
    FlattenFieldAccess().process(scope)
    #dumpscope(driver, scope)
    checkcfg(driver, scope)


def staticconstopt(driver):
    StaticConstOpt().process_all(driver)


def earlyconstopt_nonssa(driver, scope):
    EarlyConstantOptNonSSA().process(scope)
    checkcfg(driver, scope)


def constopt(driver, scope):
    ConstantOpt().process(scope)


def copyopt(driver, scope):
    CopyOpt().process(scope)


def phiopt(dfiver, scope):
    PHIInlining().process(scope)


def checkcfg(driver, scope):
    if env.dev_debug_mode:
        CFGChecker().process(scope)


def loop(driver, scope):
    LoopDetector().process(scope)
    #LoopRegionSetter().process(scope)
    LoopInfoSetter().process(scope)
    LoopDependencyDetector().process(scope)
    checkcfg(driver, scope)


def looptrans(driver, scope):
    if LoopFlatten().process(scope):
        usedef(driver, scope)
        hyperblock(driver, scope)
        loop(driver, scope)
        reduceblk(driver, scope)


def unroll(driver, scope):
    while LoopUnroller().process(scope):
        dumpscope(driver, scope)
        usedef(driver, scope)
        checkcfg(driver, scope)
        reduceblk(driver, scope)
        PolyadConstantFolding().process(scope)
        pathexp(driver, scope)
        dumpscope(driver, scope)
        usedef(driver, scope)
        constopt(driver, scope)
        usedef(driver, scope)
        copyopt(driver, scope)
        deadcode(driver, scope)
        LoopInfoSetter().process(scope)
        LoopRegionSetter().process(scope)
        LoopDependencyDetector().process(scope)


def deadcode(driver, scope):
    DeadCodeEliminator().process(scope)


def aliasvar(driver, scope):
    AliasVarDetector().process(scope)


def tempbit(driver, scope):
    TempVarWidthSetter().process(scope)


def dfg(driver, scope):
    DFGBuilder().process(scope)


def schedule(driver, scope):
    Scheduler().schedule(scope)


def createhdlscope(driver, scope):
    assert is_hdl_scope(scope)
    if HDLModule.is_hdlmodule_scope(scope):
        hdl = HDLModule(scope, scope.base_name, scope.qualified_name())
    else:
        hdl = HDLScope(scope, scope.base_name, scope.qualified_name())
    env.append_hdlscope(hdl)
    if scope.is_instantiated():
        for b in scope.bases:
            if env.hdlscope(b) is None:
                basemodule = HDLModule(b, b.base_name, b.qualified_name())
                env.append_hdlscope(basemodule)


# def hdlmodule(scope):
#     hdlscope = env.hdlscope(scope)
#     HDLModule.is_hdlmodule_scope(scope)


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


def ahdlusedef(driver, scope):
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


def genhdl(hdlmodule):
    if not hdlmodule.scope.is_testbench():
        vcodegen = VerilogCodeGen(hdlmodule)
    else:
        vcodegen = VerilogTestGen(hdlmodule)
    vcodegen.generate()
    return vcodegen.result()


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
        preprocess_global,

        dbg(dumpscope),
        iftrans,
        dbg(dumpscope),
        reduceblk,
        earlyquadruple,
        dbg(dumpscope),
        earlytypeprop,

        filter_scope(is_static_scope),
        latequadruple,
        dbg(dumpscope),
        earlyrestrictioncheck,
        usedef,
        staticconstopt,
        evaltype,

        statictypeprop,
        dbg(dumpscope),
        typecheck,
        restrictioncheck,
        usedef,

        filter_scope(is_not_static_scope),
        scopegraph,
        flipport,
        dbg(dumpscope),
        connectport,
        typeprop,
        dbg(dumpscope),
        assigncheck,
        latequadruple,
        ifcondtrans,
        dbg(dumpscope),
        earlyrestrictioncheck,
        earlytypecheck,
        typeprop,
        specworker,
        restrictioncheck,
        phase(env.PHASE_1),
        usedef,
        earlyconstopt_nonssa,
        synthcheck,
        dbg(dumpscope),
        inlineopt,
        dbg(dumpscope),

        filter_scope(is_uninlined_scope),
        setsynthparams,
        dbg(dumpscope),
        reduceblk,
        earlypathexp,
        dbg(dumpscope),
        phase(env.PHASE_2),
        usedef,
        flattenmodule,
        objssa,
        dbg(dumpscope),
        objcopyopt,
        dbg(dumpscope),
        usedef,
        objtrans,
        dbg(dumpscope),
        scalarize,
        dbg(dumpscope),
        scopegraph,
        dbg(dumpscope),
        usedef,
        scalarssa,
        #dumpcfgimg,
        dbg(dumpscope),
        usedef,
        hyperblock,
        dbg(dumpscope),
        reduceblk,
        dbg(dumpscope),
        typeprop,
        dbg(dumpscope),
        usedef,
        copyopt,
        phiopt,
        dbg(dumpscope),
        usedef,
        constopt,
        usedef,
        deadcode,
        dbg(dumpscope),
        phase(env.PHASE_3),
        instantiate,
        dbg(dumpscope),
        fieldusedef,
        postinstantiate,
        filter_scope(is_synthesis_target_scope),
        dbg(dumpscope),
        evaltype,
        stricttypeprop,
        typecheck,
        #dbg(dumpdependimg),
        dbg(dumpscope),
        usedef,
        copyopt,
        usedef,
        constopt,
        usedef,
        deadcode,
        dbg(dumpscope),
        reduceblk,
        usedef,
        loop,
        looptrans,
        laterestrictioncheck,
        dbg(dumpscope),
        unroll,
        dbg(dumpscope),
        pathexp,
        usedef,
        removelphi,
        dbg(dumpscope),
        phase(env.PHASE_4),
        usedef,
        convport,
        scopegraph,
        phase(env.PHASE_5),
        fieldusedef,
        aliasvar,
        tempbit,
        dbg(dumpscope),
        dfg,
        dbg(dumpdfg),
        schedule,
        #dumpdfgimg,
        dbg(dumpsched),
        assertioncheck,
        filter_scope(is_hdl_scope),
        phase(env.PHASE_GEN_HDL),
        createhdlscope,
        filter_scope(is_hdlmodule_scope),
        stg,
        dbg(dumpstg),
        buildmodule,
        ahdlopt(ahdlusedef),
        ahdlopt(ahdlcopyopt),
        ahdlopt(reducebits),
        #ahdlopt(reducereg),
        dbg(dumpmodule),
        transformio,
        dbg(dumpmodule),
        reducestate,
        dbg(dumpmodule),
        transformwait,
        dbg(dumpmodule),
        canonicalize,
    ]
    plan = [p for p in plan if p is not None]
    return plan


def initialize():
    env.__init__()
    Symbol.initialize()


def setup(src_file, options):
    initialize()
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
    scopes = Scope.get_scopes(bottom_up=False,
                              with_global=True,
                              with_class=True,
                              with_lib=True)
    # parse_targets(scopes)
    driver = Driver(plan, scopes)
    driver.run()
    return driver.scopes


def compile_main(src_file, options):
    setup(src_file, options)
    main_source = read_source(src_file)
    scopes = compile(compile_plan(), main_source, src_file)
    output_hdl(scopes, options)
    env.destroy()


def output_hdl(compiled_scopes, options):
    results = []
    for s in compiled_scopes:
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

