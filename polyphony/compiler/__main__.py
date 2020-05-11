import argparse
import json
import os
import sys
from .ahdlusedef import AHDLUseDefDetector
from .ahdlopt import AHDLCopyOpt
from .bitwidth import BitwidthReducer
from .bitwidth import TempVarWidthSetter
from .builtin import builtin_symbols
from .cfgopt import BlockReducer, PathExpTracer
from .cfgopt import HyperBlockBuilder
from .common import read_source
from .constopt import ConstantOpt
from .constopt import EarlyConstantOptNonSSA
from .constopt import PolyadConstantFolding
from .constopt import StaticConstOpt
from .copyopt import CopyOpt, ObjCopyOpt
from .dataflow import DFGBuilder
from .deadcode import DeadCodeEliminator
from .diagnostic import CFGChecker
from .driver import Driver
from .env import env
from .errors import CompileError, InterpretError
from .hdlgen import HDLModuleBuilder
from .hdlmodule import HDLModule
from .iftransform import IfTransformer, IfCondTransformer
from .inlineopt import InlineOpt
from .inlineopt import FlattenFieldAccess, FlattenObjectArgs, FlattenModule
from .inlineopt import ObjectHierarchyCopier
from .inlineopt import SpecializeWorker
from .instantiator import ModuleInstantiator, WorkerInstantiator
from .instantiator import EarlyModuleInstantiator, EarlyWorkerInstantiator
from .iotransformer import IOTransformer
from .iotransformer import WaitTransformer
from .irtranslator import IRTranslator
from .loopdetector import LoopDetector
from .loopdetector import LoopInfoSetter
from .loopdetector import LoopRegionSetter
from .loopdetector import LoopDependencyDetector
from .looptransformer import LoopFlatten
from .objtransform import ObjectTransformer
from .phiopt import PHIInlining, LPHIRemover
from .portconverter import PortConverter, FlattenPortList
from .portconverter import FlippedTransformer
from .portconverter import PortConnector
from .pure import interpret, PureCtorBuilder, PureFuncExecutor
from .quadruplet import EarlyQuadrupleMaker
from .quadruplet import LateQuadrupleMaker
from .regreducer import RegReducer
from .regreducer import AliasVarDetector
from .scheduler import Scheduler
from .scope import Scope
from .scopegraph import CallGraphBuilder
from .scopegraph import DependencyGraphBuilder
from .setlineno import SourceDump
from .ssa import ScalarSSATransformer
from .ssa import TupleSSATransformer
from .ssa import ListSSATransformer
from .ssa import ObjectSSATransformer
from .statereducer import StateReducer
from .stg import STGBuilder
from .synth import DefaultSynthParamSetter
from .typecheck import TypePropagation
from .typecheck import TypeSpecializer
from .typecheck import InstanceTypePropagation
from .typecheck import StaticTypePropagation
from .typecheck import TypeChecker
from .typecheck import PortAssignChecker
from .typecheck import EarlyRestrictionChecker, RestrictionChecker, LateRestrictionChecker
from .typecheck import AssertionChecker
from .typecheck import SynthesisParamChecker
from .typecheck import TypeEvalVisitor
from .unroll import LoopUnroller
from .usedef import UseDefDetector
from .usedef import FieldUseDef
from .vericodegen import VerilogCodeGen
from .veritestgen import VerilogTestGen
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


def is_hdlmodule_scope(scope):
    if ((scope.is_module() and scope.is_instantiated())
            or scope.is_function_module()
            or scope.is_testbench()):
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
    for s in uncalled_scopes:
        if s.is_namespace() or s.is_class() or s.is_worker():
            continue
        if s.is_ctor() and s.parent.is_module() and s.parent in driver.scopes:
            continue
        driver.remove_scope(s)
        Scope.destroy(s)
    for s in unused_scopes:
        if s.is_namespace():
            continue
        if s.is_builtin() and s.is_typeclass():
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


def flattenport(driver, scope):
    FlattenPortList().process(scope)


def convport(driver):
    PortConverter().process_all()


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
    SynthesisParamChecker().process(scope)


def detectrom(driver):
    #RomDetector().process_all()
    pass

def specworker(driver, scope):
    new_workers = SpecializeWorker().process(scope)
    for w in new_workers:
        driver.insert_scope(w)


def earlyinstantiate(driver):
    new_modules = EarlyModuleInstantiator().process_all()
    for module in new_modules:
        assert module.name in env.scopes
        driver.insert_scope(module)
        assert module.is_module()

    new_workers, orig_workers = EarlyWorkerInstantiator().process_all()
    for worker in new_workers:
        assert worker.name in env.scopes
        driver.insert_scope(worker)
        assert worker.is_worker()
    for orig_worker in orig_workers:
        driver.remove_scope(orig_worker)
        Scope.destroy(orig_worker)
    modules = [scope for scope in env.scopes.values() if scope.is_module()]
    for m in modules:
        if m.find_ctor().is_pure() and not m.is_instantiated():
            for child in m.children:
                driver.remove_scope(child)
                Scope.destroy(child)
            driver.remove_scope(m)
            Scope.destroy(m)


def instantiate(driver):
    new_modules = ModuleInstantiator().process_all()
    for module in new_modules:
        assert module.name in env.scopes
        assert module.is_module()
        driver.insert_scope(module)

        for s in module.collect_scope():
            if not s.is_instantiated():
                continue
            driver.insert_scope(s)
            usedef(driver, s)
            constopt(driver, s)
    TypePropagation().process_all()
    if new_modules:
        InstanceTypePropagation().process_all()
    new_scopes = WorkerInstantiator().process_all()
    for s in new_scopes:
        assert s.name in env.scopes
        driver.insert_scope(s)


def postinstantiate(driver):
    scopes = driver.get_scopes(with_global=False,
                               with_class=True,
                               with_lib=False)
    scopes = [scope for scope in scopes if scope.is_instantiated()]
    if not scopes:
        return
    for s in scopes:
        if env.config.enable_pure:
            execpure(driver, s)
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
    FlattenFieldAccess().process(scope)
    checkcfg(driver, scope)


def staticconstopt(driver):
    scopes = driver.get_scopes(bottom_up=True,
                               with_global=True,
                               with_class=True,
                               with_lib=True)
    StaticConstOpt().process_scopes(scopes)


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


def createhdlmodule(driver, scope):
    assert is_hdlmodule_scope(scope)
    hdlmodule = HDLModule(scope, scope.base_name, scope.qualified_name())
    env.append_hdlmodule(hdlmodule)
    if scope.is_instantiated():
        for b in scope.bases:
            if env.hdlmodule(b) is None:
                basemodule = HDLModule(b, b.base_name, b.qualified_name())
                env.append_hdlmodule(basemodule)


def stg(driver, scope):
    hdlmodule = env.hdlmodule(scope)
    STGBuilder().process(hdlmodule)


def reducestate(driver, scope):
    hdlmodule = env.hdlmodule(scope)
    StateReducer().process(hdlmodule)


def transformio(driver, scope):
    hdlmodule = env.hdlmodule(scope)
    IOTransformer().process(hdlmodule)


def transformwait(driver, scope):
    hdlmodule = env.hdlmodule(scope)
    WaitTransformer().process(hdlmodule)


def reducereg(driver, scope):
    hdlmodule = env.hdlmodule(scope)
    RegReducer().process(hdlmodule)


def ahdlcopyopt(driver, scope):
    hdlmodule = env.hdlmodule(scope)
    AHDLCopyOpt().process(hdlmodule)


def reducebits(driver, scope):
    hdlmodule = env.hdlmodule(scope)
    BitwidthReducer().process(hdlmodule)


def buildmodule(driver, scope):
    hdlmodule = env.hdlmodule(scope)
    modulebuilder = HDLModuleBuilder.create(hdlmodule)
    assert modulebuilder
    modulebuilder.process(hdlmodule)


def ahdlusedef(driver, scope):
    hdlmodule = env.hdlmodule(scope)
    AHDLUseDefDetector().process(hdlmodule)


def genhdl(driver, scope):
    hdlmodule = env.hdlmodule(scope)
    if not hdlmodule.scope.is_testbench():
        vcodegen = VerilogCodeGen(hdlmodule)
    else:
        vcodegen = VerilogTestGen(hdlmodule)
    vcodegen.generate()
    driver.set_result(hdlmodule.scope, vcodegen.result())


def dumpscope(driver, scope):
    driver.logger.debug(str(scope))


def dumpcfgimg(driver, scope):
    from .scope import write_dot
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
    hdlmodule = env.hdlmodule(scope)
    for fsm in hdlmodule.fsms.values():
        for stg in fsm.stgs:
            driver.logger.debug(str(stg))


def dumpmodule(driver, scope):
    hdlmodule = env.hdlmodule(scope)
    logger.debug(str(hdlmodule))


def dumphdl(driver, scope):
    logger.debug(driver.result(scope))


def printresouces(driver, scope):
    hdlmodule = env.hdlmodule(scope)
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
        pure(earlyinstantiate),
        pure(buildpurector),

        dbg(dumpscope),
        iftrans,
        reduceblk,
        earlyquadruple,
        dbg(dumpscope),
        earlytypeprop,

        filter_scope(is_static_scope),
        latequadruple,
        dbg(dumpscope),
        earlyrestrictioncheck,
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
        #typecheck,
        #flattenport,
        typeprop,
        specworker,
        restrictioncheck,
        phase(env.PHASE_1),
        usedef,
        earlyconstopt_nonssa,
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
        pure(execpureall),
        phase(env.PHASE_3),
        instantiate,
        fieldusedef,
        postinstantiate,
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
        synthcheck,
        dbg(dumpdfg),
        schedule,
        #dumpdfgimg,
        dbg(dumpsched),
        assertioncheck,
        filter_scope(is_hdlmodule_scope),
        phase(env.PHASE_GEN_HDL),
        createhdlmodule,
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
        genhdl,
        dbg(dumphdl),
        dbg(printresouces),
    ]
    plan = [p for p in plan if p is not None]
    return plan


def setup(src_file, options):
    env.__init__()
    env.dev_debug_mode = options.debug_mode
    env.verbose_level = options.verbose_level if options.verbose_level else 0
    env.quiet_level = options.quiet_level if options.quiet_level else 0
    env.enable_verilog_dump = options.verilog_dump
    env.enable_verilog_monitor = options.verilog_monitor
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


def compile(plan, source, src_file=''):
    translator = IRTranslator()
    translator.translate(source, '')
    if env.config.enable_pure:
        interpret(source, src_file)
    scopes = Scope.get_scopes(bottom_up=False,
                              with_global=True,
                              with_class=True,
                              with_lib=True)
    driver = Driver(plan, scopes)
    driver.run()
    return driver.codes


def compile_main(src_file, options):
    setup(src_file, options)
    main_source = read_source(src_file)
    compile_results = compile(compile_plan(), main_source, src_file)
    output_individual(compile_results, options.output_name, options.output_dir)
    env.destroy()


def output_individual(compile_results, output_name, output_dir):
    d = output_dir if output_dir else './'
    if d[-1] != '/':
        d += '/'

    scopes = Scope.get_scopes(with_class=True)
    scopes = [scope for scope in scopes
              if (scope.is_testbench() or
                  (scope.is_module() and scope.is_instantiated()) or
                  scope.is_function_module())]
    if output_name.endswith('.v'):
        output_name = output_name[:-2]
    with open(d + output_name + '.v', 'w') as f:
        for scope in scopes:
            if scope not in compile_results:
                continue
            code = compile_results[scope]
            if not code:
                continue
            scope_name = scope.qualified_name()
            file_name = '{}.v'.format(scope_name)
            if output_name.upper() == scope_name.upper():
                file_name = '_' + file_name
            with open('{}{}'.format(d, file_name), 'w') as f2:
                f2.write(code)
            if scope.is_testbench():
                env.append_testbench(scope)
            else:
                f.write('`include "./{}"\n'.format(file_name))
        for lib in env.using_libs:
            f.write(lib)


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
