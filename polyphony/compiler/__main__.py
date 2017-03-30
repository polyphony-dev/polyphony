import os
import sys
from optparse import OptionParser
from .builtin import builtin_symbols
from .driver import Driver
from .env import env
from .common import read_source
from .scope import Scope
from .block import BlockReducer, PathExpTracer
from .irtranslator import IRTranslator
from .typecheck import TypePropagation, InstanceTypePropagation
from .typecheck import TypeChecker, RestrictionChecker, LateRestrictionChecker, ModuleChecker
from .typecheck import AssertionChecker
from .quadruplet import QuadrupleMaker
from .hdlgen import HDLModuleBuilder
from .vericodegen import VerilogCodeGen
from .veritestgen import VerilogTestGen
from .stg import STGBuilder
from .dataflow import DFGBuilder
from .ssa import ScalarSSATransformer, TupleSSATransformer, ObjectSSATransformer
from .usedef import UseDefDetector
from .scheduler import Scheduler
from .phiresolve import PHICondResolver
from .liveness import Liveness
from .memorytransform import MemoryRenamer, RomDetector
from .memref import MemRefGraphBuilder, MemInstanceGraphBuilder
from .constopt import ConstantOpt, GlobalConstantOpt
from .constopt import ConstantOptPreDetectROM, EarlyConstantOptNonSSA
from .iftransform import IfTransformer
from .setlineno import LineNumberSetter, SourceDump
from .loopdetector import LoopDetector
from .specfunc import SpecializedFunctionMaker
from .instantiator import ModuleInstantiator, WorkerInstantiator
from .selectorbuilder import SelectorBuilder
from .inlineopt import InlineOpt, FlattenFieldAccess, AliasReplacer, ObjectHierarchyCopier
from .copyopt import CopyOpt
from .callgraph import CallGraphBuilder
from .statereducer import StateReducer
from .portconverter import PortConverter
from .ahdlusedef import AHDLUseDefDetector
from .regreducer import RegReducer
from .regreducer import AliasVarDetector
from .bitwidth import BitwidthReducer
from .iotransformer import IOTransformer
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
        if Scope.is_unremoveable(s):
            continue
        driver.remove_scope(s)
        Scope.destroy(s)


def iftrans(driver, scope):
    IfTransformer().process(scope)


def reduceblk(driver, scope):
    BlockReducer().process(scope)


def pathexp(driver, scope):
    PathExpTracer().process(scope)


def convport(driver):
    PortConverter().process_all()


def quadruple(driver, scope):
    QuadrupleMaker().process(scope)


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
            ConstantOpt().process(child)
    InstanceTypePropagation().process_all()

    new_workers = WorkerInstantiator().process_all()
    for worker in new_workers:
        assert worker.name in env.scopes
        driver.insert_scope(worker)

        assert worker.is_worker()
        ConstantOpt().process(worker)
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


def scalarize(driver, scope):
    TupleSSATransformer().process(scope)
    ObjectHierarchyCopier().process(scope)
    usedef(driver, scope)
    ObjectSSATransformer().process(scope)
    usedef(driver, scope)
    AliasReplacer().process(scope)
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


def liveness(driver, scope):
    Liveness().process(scope)


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


def compile_plan():
    def dbg(proc):
        return proc if env.dev_debug_mode else None

    def ahdlopt(proc):
        return proc if env.enable_ahdl_opt else None

    plan = [
        preprocess_global,
        iftrans,
        reduceblk,
        dbg(dumpscope),
        earlytypeprop,
        dbg(dumpscope),
        quadruple,
        typeprop,
        dbg(dumpscope),
        callgraph,
        typecheck,
        restrictioncheck,
        dbg(dumpscope),
        phase(env.PHASE_1),
        dbg(dumpscope),
        earlyconstopt_nonssa,
        dbg(dumpscope),
        inlineopt,
        reduceblk,
        pathexp,
        dbg(dumpscope),
        phase(env.PHASE_2),
        usedef,
        scalarize,
        dbg(dumpscope),
        usedef,
        scalarssa,
        dbg(dumpscope),
        usedef,
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
        instantiate,
        modulecheck,
        dbg(dumpscope),
        convport,
        dbg(dumpscope),
        usedef,
        phi,
        usedef,
        dbg(dumpscope),
        reduceblk,
        pathexp,
        dbg(dumpscope),
        phase(env.PHASE_3),
        usedef,
        loop,
        phase(env.PHASE_4),
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
    ]
    plan = [p for p in plan if p is not None]
    return plan


def compile_main(src_file, output_name, output_dir, debug_mode=False):
    env.__init__()
    env.dev_debug_mode = debug_mode
    if debug_mode:
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
    g = Scope.create(None, '@top', ['global', 'namespace'], lineno=1)
    for sym in builtin_symbols.values():
        g.import_sym(sym)
    translator.translate(read_source(src_file), '')

    scopes = Scope.get_scopes(bottom_up=False, with_global=True, with_class=True)
    driver = Driver(compile_plan(), scopes)
    driver.run()
    output_individual(driver, output_name, output_dir)


def output_individual(driver, output_name, output_dir):
    d = output_dir if output_dir else './'
    if d[-1] != '/':
        d += '/'

    scopes = Scope.get_scopes(with_class=True)
    if output_name.endswith('.v'):
        output_name = output_name[:-2]
    with open(d + output_name + '.v', 'w') as f:
        for scope in scopes:
            code = driver.result(scope)
            if not code:
                continue
            file_name = '{}.v'.format(scope.orig_name)
            if output_name.upper() == scope.orig_name.upper():
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
    usage = "usage: %prog [Options] [Python source file]"
    parser = OptionParser(usage)
    parser.add_option("-o", "--output", dest="output_name",
                      default='polyphony_out',
                      help="output filename (default is 'polyphony_out')",
                      metavar="FILE")
    parser.add_option("-d", "--dir", dest="output_dir",
                      help="output directory", metavar="DIR")
    parser.add_option("-v", dest="verbose", action="store_true",
                      help="verbose output")
    parser.add_option("-D", "--debug", dest="debug_mode", action="store_true",
                      help="enable debug mode")
    parser.add_option("-V", "--version", dest="version", action="store_true",
                      help="print the Polyphony version number")

    options, args = parser.parse_args()
    if options.version:
        from .. version import __version__
        print('Polyphony', __version__)
        sys.exit(0)
    if len(sys.argv) <= 1:
        parser.print_help()
        sys.exit(0)
    src_file = sys.argv[-1]
    if not os.path.isfile(src_file):
        print(src_file + ' is not valid file name')
        parser.print_help()
        sys.exit(0)
    if options.verbose:
        logging.basicConfig(level=logging.INFO)

    compile_main(src_file, options.output_name, options.output_dir, options.debug_mode)
