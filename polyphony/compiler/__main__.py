import os, sys
from optparse import OptionParser
from .driver import Driver
from .env import env
from .common import read_source, src_text, get_src_text
from .scope import Scope
from .block import BlockReducer, PathExpTracer
from .symbol import Symbol
from .irtranslator import IRTranslator
from .typecheck import TypePropagation, TypeChecker, ClassFieldChecker
from .quadruplet import QuadrupleMaker
from .hdlgen import HDLGenPreprocessor
from .vericodegen import VerilogCodeGen, VerilogTopGen
from .veritestgen import VerilogTestGen
from .treebalancer import TreeBalancer
from .stg import STGBuilder
from .dataflow import DFGBuilder
from .ssa import ScalarSSATransformer, TupleSSATransformer, ObjectSSATransformer
from .usedef import UseDefDetector
from .scheduler import Scheduler
from .phiresolve import PHICondResolver
from .liveness import Liveness
from .memorytransform import MemoryRenamer, RomDetector
from .memref import MemRefGraphBuilder, MemInstanceGraphBuilder
from .constantfolding import ConstantOptPreDetectROM, ConstantOpt, GlobalConstantOpt, EarlyConstantOptNonSSA
from .iftransform import IfTransformer
from .setlineno import LineNumberSetter, SourceDump
from .loopdetector import LoopDetector, SimpleLoopUnroll, LoopBlockDestructor
from .specfunc import SpecializedFunctionMaker
from .selectorbuilder import SelectorBuilder
from .inlineopt import InlineOpt, FlattenFieldAccess, AliasReplacer, ObjectHierarchyCopier
from .copyopt import CopyOpt
from .callgraph import CallGraphBuilder
from .tuple import TupleTransformer

import logging
logger = logging.getLogger()

logging_setting = {'level':logging.DEBUG, 'filename':'.tmp/debug_log', 'filemode':'w'}

def phase(phase):
    def setphase(driver):
        env.compile_phase = phase
    return setphase

def preprocess_global(driver):
    scopes = Scope.get_scopes(contain_global=True, contain_class=True)
    lineno = LineNumberSetter()
    src_dump = SourceDump()

    for s in scopes:
        lineno.process(s)
        src_dump.process(s)

    for s in (s for s in scopes if s.is_global() or s.is_class()):
        GlobalConstantOpt().process(s)

def callgraph(driver, scope):
    CallGraphBuilder().process(scope)

def tracepath(driver, scope):
    PathTracer().process(scope)

def iftrans(driver, scope):
    IfTransformer().process(scope)

def reduceblk(driver, scope):
    BlockReducer().process(scope)
    PathExpTracer().process(scope)

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
    TypePropagation().propagate_global_function_type()

def typeprop(driver, scope):
    TypePropagation().process(scope)

def typecheck(driver, scope):
    TypeChecker().process(scope)

def classcheck(driver):
    ClassFieldChecker().process_all()

def detectrom(driver):
    RomDetector().process_all()

def specfunc(driver):
    new_scopes, unused_scopes = SpecializedFunctionMaker().process_all()
    for s in new_scopes:
        assert s.name in env.scopes
        driver.insert_scope(s)
    for s in unused_scopes:
        driver.remove_scope(s)
        env.remove_scope(s)

def inlineopt(driver):
    unused_scopes = InlineOpt().process_all()
    for s in unused_scopes:
        driver.remove_scope(s)
        env.remove_scope(s)

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

def tbopt(driver, scope):
    if scope.is_testbench():
        SimpleLoopUnroll().process(scope)
        LoopBlockDestructor().process(scope)
        usedef(driver, scope)
        TupleSSATransformer().process(scope)
        scalarssa(driver, scope)
        dumpscope(driver, scope)
        usedef(driver, scope)
        memrename(driver, scope)
        dumpscope(driver, scope)
        ConstantOpt().process(scope)
        reduceblk(driver, scope)
        usedef(driver, scope)
        phi(driver, scope)
        usedef(driver, scope)
        LoopDetector().process(scope)

def liveness(driver, scope):
    Liveness().process(scope)

def dfg(driver, scope):
    DFGBuilder().process(scope)

def schedule(driver, scope):
    Scheduler().schedule(scope)

def stg(driver, scope):
    STGBuilder().process(scope)

def genhdl(driver, scope):
    if scope.is_method():
        return
    preprocessor = HDLGenPreprocessor()
    if scope.is_class() or scope.is_method():
        # workaround for inline version
        return
        #if not scope.children:
        #    return
        #scope.module_info = preprocessor.process_class(scope)
    else:
        scope.module_info = preprocessor.process_func(scope)

    SelectorBuilder().process(scope)

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
        dfg.dump()

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

    plan = [
        preprocess_global,
        iftrans,
        reduceblk,
        quadruple,
        earlytypeprop,
        typecheck,
        dbg(dumpscope),
        callgraph,
        dbg(dumpscope),
        phase(env.PHASE_1),
        dbg(dumpscope),
        earlyconstopt_nonssa,
        dbg(dumpscope),
        classcheck,
        inlineopt,
        reduceblk,
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
        detectrom,
        dbg(dumpmrg),
        usedef,
        constopt,
        dbg(dumpscope),
        usedef,
        phi,
        usedef,
        specfunc,
        dbg(dumpscope),
        usedef,
        reduceblk,
        dbg(dumpscope),
        phase(env.PHASE_3),
        usedef,
        loop,
        tbopt,
        phase(env.PHASE_4),
        dbg(dumpscope),
        dfg,
        schedule,
        dbg(dumpsched),
        meminstgraph,
        dbg(dumpmrg),
        stg,
        dbg(dumpstg),
        phase(env.PHASE_GEN_HDL),
        genhdl,
        dbg(dumpmodule),
        dbg(dumphdl),
    ]
    plan = [p for p in plan if p is not None]
    return plan


def compile_main(src_file, output_name, output_dir, debug_mode=False):
    env.__init__()
    env.dev_debug_mode = debug_mode
    if debug_mode:
        logging.basicConfig(**logging_setting)

    IRTranslator().translate(read_source(src_file))

    scopes = Scope.get_scopes(bottom_up=False, contain_class=True)
    driver = Driver(compile_plan(), scopes)
    driver.run()
    #output_all(driver, output_name, output_dir)
    output_individual(driver, output_name, output_dir)

def output_all(driver, output_name, output_dir):
    codes = []
    d = output_dir if output_dir else './'
    if d[-1] != '/': d += '/'

    scopes = Scope.get_scopes(contain_class=True)
    for scope in scopes:
        if not scope.is_testbench():
            codes.append(driver.result(scope))
        else:
            with open('{}{}_{}.v'.format(d, output_name, scope.orig_name), 'w') as f:
                if driver.result(scope):
                    f.write(driver.result(scope))

    mains = []
    for scope in scopes:
        if scope.is_main():
            mains.append(env.scopes[scope.name].module_info)

    with open(d + output_name + '.v', 'w') as f:
        for code in codes:
            if code:
                f.write(code)
        if mains:
            topgen = VerilogTopGen(mains)
            logger.debug('--------------------------')
            logger.debug('HDL top module generation ... ')
            topgen.generate()
            logger.debug('--------------------------')
            logger.debug(topgen.result())
            result = topgen.result()
            f.write(result)
        for lib in env.using_libs:
            f.write(lib)

def output_individual(driver, output_name, output_dir):
    codes = []
    d = output_dir if output_dir else './'
    if d[-1] != '/': d += '/'

    # workaround for inline version
    scopes = Scope.get_scopes(contain_class=False)
    #scopes = Scope.get_scopes(contain_class=True)
    with open(d + output_name + '.v', 'w') as f:
        for scope in scopes:
            file_name = '{}_{}.v'.format(output_name, scope.orig_name)
            with open('{}{}'.format(d, file_name), 'w') as f2:
                if driver.result(scope):
                    f2.write(driver.result(scope))
            if not scope.is_testbench():
                f.write('`include "./{}"\n'.format(file_name))
        for lib in env.using_libs:
            f.write(lib)
def main():
    usage = "usage: %prog [Options] [Python source file]"
    parser = OptionParser(usage)
    parser.add_option("-o", "--output", dest="output_name",
                      default='polyphony_out',
                      help="output filename (default is 'polyphony_out')", metavar="FILE")
    parser.add_option("-d", "--dir", dest="output_dir",
                      help="output directory", metavar="DIR")
    parser.add_option("-v", dest="verbose", action="store_true", 
                      help="verbose output")
    parser.add_option("-D", "--debug", dest="debug_mode", action="store_true", 
                      help="enable debug mode")

    options, args = parser.parse_args()
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

