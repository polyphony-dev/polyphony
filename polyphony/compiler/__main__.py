import argparse
import os
import sys
from .ahdlusedef import AHDLUseDefDetector
from .bitwidth import BitwidthReducer
from .builtin import builtin_symbols
from .callgraph import CallGraphBuilder
from .cfgopt import BlockReducer, PathExpTracer
from .cfgopt import HyperBlockBuilder
from .common import read_source
from .constopt import ConstantOpt, GlobalConstantOpt
from .constopt import ConstantOptPreDetectROM, EarlyConstantOptNonSSA
from .copyopt import CopyOpt
from .dataflow import DFGBuilder
from .deadcode import DeadCodeEliminator
from .driver import Driver
from .env import env
from .errors import CompileError, InterpretError
from .hdlgen import HDLModuleBuilder
from .iftransform import IfTransformer
from .inlineopt import InlineOpt
from .inlineopt import FlattenFieldAccess, FlattenObjectArgs, FlattenModule
from .inlineopt import AliasReplacer, ObjectHierarchyCopier
from .instantiator import ModuleInstantiator, WorkerInstantiator
from .instantiator import EarlyModuleInstantiator, EarlyWorkerInstantiator
from .iotransformer import IOTransformer
from .irtranslator import IRTranslator
from .loopdetector import LoopDetector
from .memorytransform import MemoryRenamer, RomDetector
from .memref import MemRefGraphBuilder, MemInstanceGraphBuilder
from .phiresolve import PHICondResolver
from .portconverter import PortConverter, FlattenPortList
from .pure import interpret, PureCtorBuilder, PureFuncExecutor
from .quadruplet import EarlyQuadrupleMaker
from .quadruplet import LateQuadrupleMaker
from .regreducer import RegReducer
from .regreducer import AliasVarDetector
from .scheduler import Scheduler
from .scope import Scope
from .selectorbuilder import SelectorBuilder
from .setlineno import LineNumberSetter, SourceDump
from .specfunc import SpecializedFunctionMaker
from .ssa import ScalarSSATransformer, TupleSSATransformer, ObjectSSATransformer
from .statereducer import StateReducer
from .stg import STGBuilder
from .typecheck import TypePropagation, InstanceTypePropagation
from .typecheck import TypeChecker, RestrictionChecker, LateRestrictionChecker, ModuleChecker
from .typecheck import AssertionChecker
from .usedef import UseDefDetector
from .vericodegen import VerilogCodeGen
from .veritestgen import VerilogTestGen
import logging
logger = logging.getLogger()

logging_setting = {
    'level': logging.DEBUG,
    'filename': '.tmp/debug_log',
    'filemode': 'w'
}


def phase(phase):
    def setphase(driver):
        env.compile_phase = phase
    return setphase


def preprocess_global(driver):
    scopes = Scope.get_scopes(with_global=True, with_class=True)
    lineno = LineNumberSetter()
    src_dump = SourceDump()

    for s in scopes:
        lineno.process(s)
        src_dump.process(s)

    scopes = Scope.get_scopes(with_global=True, with_class=True, with_lib=True)
    for s in (s for s in scopes if s.is_namespace() or (s.is_class() and not s.is_lib())):
        GlobalConstantOpt().process(s)


def callgraph(driver):
    unused_scopes = CallGraphBuilder().process_all()
    for s in unused_scopes:
        if env.compile_phase < env.PHASE_3 and Scope.is_unremovable(s):
            continue
        driver.remove_scope(s)
        Scope.destroy(s)


def iftrans(driver, scope):
    IfTransformer().process(scope)


def reduceblk(driver, scope):
    BlockReducer().process(scope)


def pathexp(driver, scope):
    PathExpTracer().process(scope)


def hyperblock(driver, scope):
    if not env.enable_hyperblock:
        return
    if scope.is_testbench():
        return
    HyperBlockBuilder().process(scope)


def buildpurector(driver):
    new_ctors = PureCtorBuilder().process_all()
    for ctor in new_ctors:
        assert ctor.name in env.scopes
        driver.insert_scope(ctor)


def execpure(driver, scope):
    PureFuncExecutor().process(scope)


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


def scalarssa(driver, scope):
    ScalarSSATransformer().process(scope)


def phi(driver, scope):
    PHICondResolver().process(scope)


def memrefgraph(driver):
    MemRefGraphBuilder().process_all()


def meminstgraph(driver, scope):
    MemInstanceGraphBuilder().process(scope)


def memrename(driver, scope):
    MemoryRenamer().process(scope)


def earlytypeprop(driver):
    typed_scopes = TypePropagation().process_all()
    for s in typed_scopes:
        assert s.name in env.scopes
        driver.insert_scope(s)
        TypePropagation().process(s)


def typeprop(driver, scope):
    typed_scopes = TypePropagation().process(scope)
    for s in typed_scopes:
        assert s.name in env.scopes
        driver.insert_scope(s)
        TypePropagation().process(s)


def typecheck(driver, scope):
    TypeChecker().process(scope)


def restrictioncheck(driver, scope):
    RestrictionChecker().process(scope)


def modulecheck(driver, scope):
    LateRestrictionChecker().process(scope)
    ModuleChecker().process(scope)


def assertioncheck(driver, scope):
    AssertionChecker().process(scope)


def detectrom(driver):
    RomDetector().process_all()


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
        driver.insert_scope(module)
        driver.insert_scope(module.find_ctor())

        assert module.is_module()
        for child in module.children:
            if child.is_lib():
                continue
            if not (child.is_ctor() or child.is_worker()):
                continue
            usedef(driver, child)
            execpure(driver, child)
            constopt(driver, child)

    if new_modules:
        InstanceTypePropagation().process_all()

    new_workers = WorkerInstantiator().process_all()
    for worker in new_workers:
        assert worker.name in env.scopes
        driver.insert_scope(worker)

        assert worker.is_worker()
        usedef(driver, worker)
        execpure(driver, worker)
        constopt(driver, worker)
    callgraph(driver)
    detectrom(driver)


def specfunc(driver):
    new_scopes, unused_scopes = SpecializedFunctionMaker().process_all()
    for s in new_scopes:
        assert s.name in env.scopes
        driver.insert_scope(s)


def inlineopt(driver):
    InlineOpt().process_all()
    callgraph(driver)


def flattenmodule(driver, scope):
    FlattenModule(driver).process(scope)


def scalarize(driver, scope):
    TupleSSATransformer().process(scope)
    ObjectHierarchyCopier().process(scope)
    usedef(driver, scope)
    ObjectSSATransformer().process(scope)
    usedef(driver, scope)
    AliasReplacer().process(scope)

    FlattenObjectArgs().process(scope)
    FlattenFieldAccess().process(scope)


def earlyconstopt_nonssa(driver, scope):
    EarlyConstantOptNonSSA().process(scope)


def constopt_pre_detectrom(driver, scope):
    ConstantOptPreDetectROM().process(scope)


def constopt(driver, scope):
    ConstantOpt().process(scope)


def copyopt(driver, scope):
    CopyOpt().process(scope)


def loop(driver, scope):
    LoopDetector().process(scope)


def deadcode(driver, scope):
    DeadCodeEliminator().process(scope)


def dfg(driver, scope):
    DFGBuilder().process(scope)


def schedule(driver, scope):
    Scheduler().schedule(scope)


def stg(driver, scope):
    STGBuilder().process(scope)


def reducestate(driver, scope):
    StateReducer().process(scope)


def transformio(driver, scope):
    IOTransformer().process(scope)


def reducereg(driver, scope):
    RegReducer().process(scope)


def aliasvar(driver, scope):
    AliasVarDetector().process(scope)


def reducebits(driver, scope):
    BitwidthReducer().process(scope)


def buildmodule(driver, scope):
    modulebuilder = HDLModuleBuilder.create(scope)
    if modulebuilder:
        modulebuilder.process(scope)
        SelectorBuilder().process(scope)


def ahdlusedef(driver, scope):
    if not scope.module_info:
        return
    AHDLUseDefDetector().process(scope)


def genhdl(driver, scope):
    if not scope.module_info:
        return
    if not scope.is_testbench():
        vcodegen = VerilogCodeGen(scope)
    else:
        vcodegen = VerilogTestGen(scope)
    vcodegen.generate()
    driver.set_result(scope, vcodegen.result())


def dumpscope(driver, scope):
    driver.logger.debug(str(scope))


def dumpcfgimg(driver, scope):
    from .scope import write_dot
    if scope.is_function_module() or scope.is_method() or scope.is_module():
        write_dot(scope, driver.stage)


def dumpmrg(driver, scope):
    driver.logger.debug(str(env.memref_graph))


def dumpdfg(driver, scope):
    for dfg in scope.dfgs():
        driver.logger.debug(str(dfg))


def dumpsched(driver, scope):
    for dfg in scope.dfgs():
        driver.logger.debug('--- ' + dfg.name)
        for n in dfg.get_scheduled_nodes():
            driver.logger.debug(n)


def dumpstg(driver, scope):
    for stg in scope.stgs:
        driver.logger.debug(str(stg))


def dumpmodule(driver, scope):
    if scope.module_info:
        logger.debug(str(scope.module_info))


def dumphdl(driver, scope):
    logger.debug(driver.result(scope))


def printresouces(driver, scope):
    if (scope.is_function_module() or scope.is_module()):
        resources = scope.module_info.resources()
        print(resources)


def compile_plan():
    def dbg(proc):
        return proc if env.dev_debug_mode else None

    def ahdlopt(proc):
        return proc if env.enable_ahdl_opt else None

    plan = [
        preprocess_global,
        dbg(dumpscope),
        earlyinstantiate,
        buildpurector,
        iftrans,
        reduceblk,
        dbg(dumpscope),
        earlyquadruple,
        dbg(dumpscope),
        earlytypeprop,
        dbg(dumpscope),
        typeprop,
        dbg(dumpscope),
        latequadruple,
        callgraph,
        typecheck,
        flattenport,
        typeprop,
        restrictioncheck,
        phase(env.PHASE_1),
        earlyconstopt_nonssa,
        dbg(dumpscope),
        inlineopt,
        dbg(dumpscope),
        reduceblk,
        pathexp,
        dbg(dumpscope),
        phase(env.PHASE_2),
        usedef,
        flattenmodule,
        scalarize,
        dbg(dumpscope),
        usedef,
        scalarssa,
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
        dbg(dumpscope),
        usedef,
        memrename,
        dbg(dumpscope),
        usedef,
        memrefgraph,
        dbg(dumpmrg),
        dbg(dumpscope),
        constopt_pre_detectrom,
        dbg(dumpscope),
        detectrom,
        dbg(dumpmrg),
        usedef,
        constopt,
        dbg(dumpscope),
        execpure,
        phase(env.PHASE_3),
        instantiate,
        modulecheck,
        dbg(dumpscope),
        convport,
        usedef,
        copyopt,
        usedef,
        deadcode,
        dbg(dumpscope),
        reduceblk,
        usedef,
        dbg(dumpscope),
        phi,
        usedef,
        dbg(dumpscope),
        pathexp,
        dbg(dumpscope),
        phase(env.PHASE_4),
        usedef,
        loop,
        phase(env.PHASE_5),
        usedef,
        aliasvar,
        dbg(dumpscope),
        dfg,
        dbg(dumpdfg),
        schedule,
        dbg(dumpsched),
        meminstgraph,
        dbg(dumpmrg),
        assertioncheck,
        stg,
        dbg(dumpstg),
        phase(env.PHASE_GEN_HDL),
        buildmodule,
        ahdlopt(ahdlusedef),
        ahdlopt(reducebits),
        #ahdlopt(reducereg),
        dbg(dumpmodule),
        transformio,
        dbg(dumpmodule),
        reducestate,
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
    if env.dev_debug_mode:
        logging.basicConfig(**logging_setting)

    translator = IRTranslator()
    internal_root_dir = '{0}{1}{2}{1}_internal{1}'.format(
        os.path.dirname(__file__),
        os.path.sep, os.path.pardir
    )
    package_file = os.path.abspath(internal_root_dir + '_builtins.py')
    env.set_current_filename(package_file)
    translator.translate(read_source(package_file), '__builtin__')
    package_file = os.path.abspath(internal_root_dir + '_polyphony.py')
    env.set_current_filename(package_file)
    translator.translate(read_source(package_file), 'polyphony')
    for name in ('_typing', '_io', '_timing'):
        package_file = os.path.abspath(internal_root_dir + name + '.py')
        package_name = os.path.basename(package_file).split('.')[0]
        package_name = package_name[1:]
        env.set_current_filename(package_file)
        translator.translate(read_source(package_file), package_name)
    env.set_current_filename(src_file)
    g = Scope.create_namespace(None, env.global_scope_name, {'global'})
    env.push_outermost_scope(g)
    for sym in builtin_symbols.values():
        g.import_sym(sym)


def compile(plan, source, src_file=''):
    translator = IRTranslator()
    translator.translate(source, '')
    if env.enable_pure:
        interpret(source, src_file)
    scopes = Scope.get_scopes(bottom_up=False, with_global=True, with_class=True)
    driver = Driver(plan, scopes)
    driver.run()
    return driver.codes


def compile_main(src_file, options):
    setup(src_file, options)
    main_source = read_source(src_file)
    compile_results = compile(compile_plan(), main_source, src_file)
    output_individual(compile_results, options.output_name, options.output_dir)


def output_individual(compile_results, output_name, output_dir):
    d = output_dir if output_dir else './'
    if d[-1] != '/':
        d += '/'

    scopes = Scope.get_scopes(with_class=True)
    scopes = [scope for scope in scopes
              if (scope.is_testbench() or (scope.is_module() and scope.is_instantiated()) or scope.is_function_module())]
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
    parser.add_argument('-v', '--verbose', dest='verbose_level',
                        action='count', help='verbose output')
    parser.add_argument('-D', '--debug', dest='debug_mode',
                        action='store_true', help='enable debug mode')
    parser.add_argument('-q', '--quiet', dest='quiet_level',
                        action='count', help='suppress warning/error messages')
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
