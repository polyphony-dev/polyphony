import os, sys
from optparse import OptionParser
from .driver import Driver
from .env import env
from .common import read_source, src_text
from .scope import Scope
from .block import BlockTracer
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
from .ssa import SSAFormTransformer
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
from .inlineopt import InlineOpt
from .copyopt import CopyOpt
from .callgraph import CallGraphBuilder

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
    callgraph_builder = CallGraphBuilder()

    for s in scopes:
        lineno.process(s)
        src_dump.process(s)
        #callgraph_builder.process(s)

    for s in (s for s in scopes if s.is_global() or s.is_class()):
        constopt = GlobalConstantOpt()
        constopt.process(s)

    typepropagation = TypePropagation()
    typepropagation.propagate_global_function_type()

def iftrans(driver, scope):
    if_transformer = IfTransformer()
    if_transformer.process(scope)

def traceblk(driver, scope):
    bt = BlockTracer()
    bt.process(scope)

def quadruple(driver, scope):
    quadruple = QuadrupleMaker()
    quadruple.process(scope)

def usedef(driver, scope):
    udd = UseDefDetector()
    udd.process(scope)

def ssa(driver, scope):
    ssa = SSAFormTransformer()
    ssa.process(scope)

def phi(driver, scope):
    phi_cond_resolver = PHICondResolver()
    phi_cond_resolver.process(scope)

def memrefgraph(driver):
    mrg_builder = MemRefGraphBuilder()
    mrg_builder.process_all()

def meminstgraph(driver, scope):
    mrg_builder = MemInstanceGraphBuilder()
    mrg_builder.process(scope)

def memrename(driver, scope):
    mem_renamer = MemoryRenamer()
    mem_renamer.process(scope)

def typeprop(driver, scope):
    typepropagation = TypePropagation()
    typepropagation.process(scope)

def typecheck(driver, scope):
    typecheck = TypeChecker()
    typecheck.process(scope)

def classcheck(driver):
    classchecker = ClassFieldChecker()
    classchecker.process_all()

def detectrom(driver):
    rom_detector = RomDetector()
    rom_detector.process_all()

def specfunc(driver):
    spec_func_maker = SpecializedFunctionMaker()
    new_scopes, unused_scopes = spec_func_maker.process_all()
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

def earlyconstopt_nonssa(driver, scope):
    constopt = EarlyConstantOptNonSSA()
    constopt.process(scope)

def constopt_pre_detectrom(driver, scope):
    constopt = ConstantOptPreDetectROM()
    constopt.process(scope)

def constopt(driver, scope):
    constopt = ConstantOpt()
    constopt.process(scope)

def copyopt(driver, scope):
    copyopt = CopyOpt()
    copyopt.process(scope)

def loop(driver, scope):
    loop_detector = LoopDetector()
    loop_detector.process(scope)

def tbopt(driver, scope):
    if scope.is_testbench():
        simple_loop_unroll = SimpleLoopUnroll()
        simple_loop_unroll.process(scope)
        loopdestructor = LoopBlockDestructor()
        loopdestructor.process(scope)
        usedef(driver, scope)
        ssa(driver, scope)
        usedef(driver, scope)
        memrename(driver, scope),
        constopt = ConstantOpt()
        constopt.process(scope)
        traceblk(driver, scope)
        usedef(driver, scope)
        phi(driver, scope)
        usedef(driver, scope)
        loop_detector = LoopDetector()
        loop_detector.process(scope)

def liveness(driver, scope):
    liveness = Liveness()
    liveness.process(scope)

def dfg(driver, scope):
    dfg_builder = DFGBuilder()
    dfg_builder.process(scope)

def schedule(driver, scope):
    scheduler = Scheduler()
    scheduler.schedule(scope)

def stg(driver, scope):
    stg_builder = STGBuilder()
    stg_builder.process(scope)

def genhdl(driver, scope):
    if scope.is_method():
        return
    preprocessor = HDLGenPreprocessor()
    if scope.is_class():
        # workaround for inline version
        return
        #if not scope.children:
        #    return
        #scope.module_info = preprocessor.process_class(scope)
    else:
        scope.module_info = preprocessor.process_func(scope)

    selector_builder = SelectorBuilder()
    selector_builder.process(scope)

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
    plan = [
        preprocess_global,
        dumpscope,
        phase(env.PHASE_1),
        iftrans,
        traceblk,
        dumpscope,
        earlyconstopt_nonssa,
        quadruple,
        inlineopt,
        dumpscope,
        traceblk,
        dumpscope,
        usedef,
        dumpscope,
        phase(env.PHASE_2),
        usedef,
        ssa,
        dumpscope,
        usedef,
        copyopt,
        dumpscope,
        usedef,
        typeprop,
        memrename,
        dumpscope,
        #classcheck,
        usedef,
        memrefgraph,
        dumpmrg,
        dumpscope,
        typecheck,
        dumpscope,
        constopt_pre_detectrom,
        detectrom,
        dumpmrg,
        usedef,
        constopt,
        usedef,
        phi,
        usedef,
        specfunc,
        dumpscope,
        usedef,
        traceblk,
        dumpscope,
        phase(env.PHASE_3),
        usedef,
        loop,
        tbopt,
        phase(env.PHASE_4),
        dumpscope,
        dfg,
        schedule,
        dumpsched,
        meminstgraph,
        dumpmrg,
        stg,
        dumpstg,
        phase(env.PHASE_GEN_HDL),
        genhdl,
        dumpmodule,
        dumphdl
    ]
    return plan


def compile_main(src_file, output_name, output_dir):
    env.__init__()
    translator = IRTranslator()
    translator.translate(read_source(src_file))

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

    scopes = Scope.get_scopes(contain_class=True)
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
    compile_main(src_file, options.output_name, options.output_dir)

