import os, sys, traceback, profile
from optparse import OptionParser
from driver import Driver
from env import env
from common import read_source, src_text
from irtranslator import IRTranslator
from typecheck import TypePropagation, TypeChecker
from quadruplet import QuadrupleMaker
from scope import Scope
from block import BlockTracer
from symbol import Symbol
from hdlgen import HDLGenPreprocessor
from vericodegen import VerilogCodeGen, VerilogTopGen
from veritestgen import VerilogTestGen
from treebalancer import TreeBalancer
from memorylink import MemoryLinkMaker, MemoryInstanceLinkMaker
from stg import STGBuilder
from stg_opt import STGOptimizer
from dataflow import DFGBuilder
from dfg_opt import DFGOptimizer
from ssa import SSAFormTransformer
from ssa_opt import SSAOptimizer
from usedef import UseDefDetector
from jumpdependency import JumpDependencyDetector
from scheduler import Scheduler
from phiresolve import PHICondResolver
from liveness import Liveness
from memorytransform import MemoryInfoMaker, MemoryTransformer
from constantfolding import ConstantFolding
from iftransform import IfTransformer
from setlineno import LineNumberSetter, SourceDump
from loopdetector import LoopDetector, SimpleLoopUnroll
from specfunc import SpecializedFunctionMaker
import logging
logger = logging.getLogger()

logging_setting = {'level':logging.DEBUG, 'filename':'debug_log', 'filemode':'w'}

def compile_plan():
    def phase(phase):
        def setphase(driver, scope):
            env.compile_phase = phase
        return setphase
    
    def linenum(driver, scope):
        lineno = LineNumberSetter()
        lineno.process(scope)
        src_dump = SourceDump()
        src_dump.process(scope)
        
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

    def ssaopt(driver, scope):
         ssa_opt = SSAOptimizer()
         ssa_opt.process(scope)

    def ssaopt2(driver, scope):
         ssa_opt = SSAOptimizer()
         ssa_opt.eliminate_moves(scope)

    def phi(driver, scope):
         phi_cond_resolver = PHICondResolver()
         phi_cond_resolver.process(scope)

    def meminfo(driver, scope):
        meminfo_maker = MemoryInfoMaker()
        meminfo_maker.process(scope)

    def memtrans(driver, scope):
        mem_transformer = MemoryTransformer()
        mem_transformer.process(scope)

    def typecheck(driver, scope):
        typepropagation = TypePropagation()
        typepropagation.process(scope)
        typecheck = TypeChecker()
        typecheck.process(scope)

    def memlink(driver, scope):
        memory_link_maker = MemoryLinkMaker()
        memory_link_maker.process(scope)

    def specfunc(driver, scope):
        spec_func_maker = SpecializedFunctionMaker()
        new_scopes = spec_func_maker.process(scope)
        for s in new_scopes:
            env.append_scope(s)
            driver.insert_scope(s)

    def constopt(driver, scope):
        constantfolding = ConstantFolding(scope)
        constantfolding.process(scope)

    def loop(driver, scope):
        loop_detector = LoopDetector()
        loop_detector.process(scope)

    def tbopt(driver, scope):
        if scope.is_testbench():
            simple_loop_unroll = SimpleLoopUnroll()
            simple_loop_unroll.process(scope)
            usedef(driver, scope)
            ssa(driver, scope)
            usedef(driver, scope)
            ssaopt(driver, scope)
            usedef(driver, scope)
            phi(driver, scope)
            usedef(driver, scope)

    def liveness(driver, scope):
        liveness = Liveness()
        liveness.process(scope)

    def jumpdepend(driver, scope):
        jdd = JumpDependencyDetector()
        jdd.process(scope)

    def dfg(driver, scope):
        dfg_builder = DFGBuilder()
        dfg_builder.process(scope)

    def dfgopt(driver, scope):
        dfg_opt = DFGOptimizer()
        dfg_opt.process(scope)

    def schedule(driver, scope):
        scheduler = Scheduler()
        scheduler.schedule(scope)
        
    def memilink(driver, scope):
        memory_ilink_maker = MemoryInstanceLinkMaker()
        memory_ilink_maker.process(scope)

    def stg(driver, scope):
        stg_builder = STGBuilder()
        stg_builder.process(scope)

    def stgopt(driver, scope):
        stg_opt = STGOptimizer()
        stg_opt.process(scope)

    def genhdl(driver, scope):
        preprocessor = HDLGenPreprocessor()
        scope.module_info = preprocessor.phase1(scope)
        if not scope.is_testbench():
            vcodegen = VerilogCodeGen(scope)
        else:
            vcodegen = VerilogTestGen(scope)
        vcodegen.generate()
        driver.set_result(scope, vcodegen.result())

    def dumpscope(driver, scope):
        driver.logger.debug(str(scope))

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
        logger.debug(str(scope.module_info))

    def dumphdl(driver, scope):
        logger.debug(driver.result(scope))


    plan = [
        phase(env.PHASE_1),
        linenum,
        iftrans,
        traceblk,
        quadruple,
        meminfo,
        usedef,
        memtrans,
        dumpscope,
        phase(env.PHASE_2),
        usedef,
        ssa,
        dumpscope,
        usedef,
        typecheck,
        memlink,
        ssaopt,
        usedef,
        phi,
        usedef,
        ssaopt2,
        usedef,
        #specfunc,
        #dumpscope,
        phase(env.PHASE_3),
        constopt,
        usedef,
        loop,
        tbopt,
        liveness,
        jumpdepend,
        usedef,
        dumpscope,
        dfg,
        dfgopt,
        schedule,
        dumpsched,
        memilink,
        stg,
        stgopt,
        dumpstg,
        phase(env.PHASE_GEN_HDL),
        genhdl,
        dumpmodule,
        dumphdl
    ]
    return plan


def compile_main(src_file, output_name, output_dir):
    translator = IRTranslator()
    global_scope = translator.translate(read_source(src_file))

    global_constantfolding = ConstantFolding(global_scope)
    global_constantfolding.process_global()

    typepropagation = TypePropagation()
    typepropagation.propagate_global_function_type()

    scopes = Scope.get_scopes(bottom_up=False)
    driver = Driver(compile_plan(), scopes)
    driver.run()
    output_all(driver, output_name, output_dir)


def output_all(driver, output_name, output_dir):
    codes = []
    d = output_dir if output_dir else './'
    if d[-1] != '/': d += '/'

    scopes = Scope.get_scopes()
    for scope in scopes:
        if not scope.is_testbench():
            codes.append(driver.result(scope))
        else:
            with open(d + scope.orig_name + '.v', 'w') as f:
                f.write(driver.result(scope))

    mains = []
    for scope in scopes:
        if scope.is_main():
            mains.append(env.scopes[scope.name].module_info)

    with open(d + output_name + '.v', 'w') as f:
        for code in codes:
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

if __name__ == '__main__':
    logging.basicConfig(**logging_setting)
    try:
        #profile.run("main()")
        main()
    except Exception as e:
        traceback.print_exc()
        logger.exception(e)
        sys.exit(e)
    
