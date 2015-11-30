import os, sys, traceback, profile
from optparse import OptionParser
from env import env
from common import read_source, src_text
from irtranslator import IRTranslator
from typecheck import TypePropagation, TypeChecker
from callgraph import CallGraphBuilder
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
import logging
logger = logging.getLogger()

logging_setting = {'level':logging.DEBUG, 'filename':'debug_log', 'filemode':'w'}

def compile_main(src_file, output_name, output_dir):
    translator = IRTranslator()
    global_scope = translator.translate(read_source(src_file))
    global_constantfolding = ConstantFolding(global_scope)
    global_constantfolding.process_global()
    logger.debug(str(global_scope))

    typepropagation = TypePropagation()
    typepropagation.propagate_global_function_type()

    cgbuilder = CallGraphBuilder()
    env.call_graph = cgbuilder.build(global_scope)

    scopes = env.serialize_function_tree()
    compile_funcs = [
        compile_hdl_phase1,
        compile_hdl_phase2,
        compile_hdl_phase3
    ]
    for fn in compile_funcs:
        for scope in scopes:
            logger.addHandler(env.logfiles[scope])
            fn(scope)
            logger.removeHandler(env.logfiles[scope])

    codes = []
    d = output_dir if output_dir else './'
    if d[-1] != '/': d += '/'

    for scope in scopes:
        logger.addHandler(env.logfiles[scope])
        code = gen_hdl(scope)
        logger.removeHandler(env.logfiles[scope])
        if not scope.is_testbench():
            codes.append(code)
        else:
            f = open(d + scope.orig_name + '.v', 'w')
            f.write(code)
            f.close()

    mains = []
    for scope in scopes:
        if scope.is_main():
            mains.append(env.scopes[scope.name].module_info)

    f = open(d + output_name + '.v', 'w')
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
    f.close()

def compile_hdl_phase1(scope):
    '''
    phase1:
      - quadruplification
      - ssa & constant folding
    '''
    env.compile_phase = "phase1"

    lineno = LineNumberSetter()
    lineno.process(scope)
    src_dump = SourceDump()
    src_dump.process(scope)

    logger.debug('--------------------------')
    logger.debug('If transform ... ')
    if_transformer = IfTransformer()
    if_transformer.process(scope)
    logger.debug(str(scope))

    logger.debug('--------------------------')
    bt = BlockTracer()
    bt.process(scope)
    logger.debug(str(scope))

    logger.debug('--------------------------')
    logger.debug('Making quadruples ... ')
    quadruple = QuadrupleMaker()
    quadruple.process(scope)
    logger.debug(str(scope))

    logger.debug('--------------------------')
    logger.debug('use-def detecting before SSA ... ')
    udd = UseDefDetector()
    udd.process(scope)

    compile_hdl_ssa(scope)

    logger.debug('--------------------------')
    logger.debug('use-def detecting ... ')
    udd = UseDefDetector()
    udd.process(scope)
    udd.table.dump()

def compile_hdl_phase2(scope):
    '''
    phase2:
      - some memory analyzes
    '''
    env.compile_phase = "phase2"

    logger.debug('--------------------------')
    logger.debug('Making memory info ...')
    meminfo_maker = MemoryInfoMaker()
    meminfo_maker.process(scope)
    logger.debug(str(scope))

    logger.debug('--------------------------')
    logger.debug('use-def detecting ... ')
    udd = UseDefDetector()
    udd.process(scope)

    logger.debug('--------------------------')
    logger.debug('memory access tranforming ...')
    mem_transformer = MemoryTransformer()
    mem_transformer.process(scope)
    logger.debug(str(scope))

    typepropagation = TypePropagation()
    typepropagation.process(scope)
    logger.debug(str(scope))

    logger.debug('--------------------------')
    logger.debug('Check type semantics... ')
    logger.debug(str(scope))
    typecheck = TypeChecker()
    typecheck.process(scope)

    logger.debug('--------------------------')
    logger.debug('Making memory links ...')
    memory_link_maker = MemoryLinkMaker()
    memory_link_maker.process(scope)
    logger.debug(str(scope))


def compile_hdl_phase3(scope):
    '''
    phase3:
      - inlining function
      - second ssa & constant folding
      - make data flow graph
      - scheduling
      - make state transition graph
    '''
    env.compile_phase = "phase3"

    logger.debug('--------------------------')
    logger.debug('2nd constant folding ... ')
    constantfolding = ConstantFolding(scope)
    constantfolding.process(scope)
    logger.debug(str(scope))

    logger.debug('--------------------------')
    logger.debug('use-def detecting ... ')
    udd = UseDefDetector()
    udd.process(scope)

    logger.debug('Loop detecting ... ')
    loop_detector = LoopDetector()
    loop_detector.process(scope)

    if scope.is_testbench():
        simple_loop_unroll = SimpleLoopUnroll()
        simple_loop_unroll.process(scope)
        logger.debug(str(scope))

        logger.debug('--------------------------')
        logger.debug('use-def detecting ... ')
        udd = UseDefDetector()
        udd.process(scope)

        compile_hdl_ssa(scope)

        logger.debug('--------------------------')
        logger.debug('use-def detecting ... ')
        udd = UseDefDetector()
        udd.process(scope)
        udd.table.dump()

    logger.debug('--------------------------')
    logger.debug('liveness detecting ... ')
    liveness = Liveness()
    liveness.process(scope)

    logger.debug('--------------------------')
    logger.debug('jump dependency detecting ... ')
    jdd = JumpDependencyDetector()
    jdd.process(scope)
    logger.debug(str(scope))

    logger.debug('--------------------------')
    logger.debug('use-def detecting ... ')
    udd = UseDefDetector()
    udd.process(scope)

    logger.debug('--------------------------')
    logger.debug('Builing DFG ... ')
    dfg_builder = DFGBuilder()
    dfg_builder.process(scope)

    for dfg in scope.dfgs():
        dfg.dump()
    #    dfg.write_dot(scope.name)

    dfg_opt = DFGOptimizer()
    dfg_opt.process(scope)

    logger.debug('--------------------------')
    logger.debug('Scheduling ... ')
    scheduler = Scheduler()
    scheduler.schedule(scope)
    for dfg in scope.dfgs():
        logger.debug('--- ' + dfg.name)
        for n in dfg.get_scheduled_nodes():
            logger.debug(n)

    logger.debug('--------------------------')
    logger.debug('Making memory links ...')
    memory_ilink_maker = MemoryInstanceLinkMaker()
    memory_ilink_maker.process(scope)

    logger.debug('--------------------------')
    logger.debug('Build STG ... ')
    stg_builder = STGBuilder()
    stg_builder.process(scope)
    for stg in scope.stgs:
        logger.debug(str(stg))

    logger.debug('--------------------------')
    logger.debug('Optimized STG ... ')
    stg_opt = STGOptimizer()
    stg_opt.process(scope)
    for stg in scope.stgs:
        logger.debug(str(stg))


def compile_hdl_ssa(scope):
    logger.debug('--------------------------')
    logger.debug('SSA transform ... ')
    ssa = SSAFormTransformer()
    ssa.process(scope)
    logger.debug(str(scope))

    logger.debug('--------------------------')
    logger.debug('use-def detecting after SSA ... ')
    udd = UseDefDetector()
    udd.process(scope)

    logger.debug('--------------------------')
    logger.debug('SSA optimization ... ')
    ssa_opt = SSAOptimizer()
    ssa_opt.process(scope)
    logger.debug(str(scope))

    logger.debug('--------------------------')
    logger.debug('use-def detecting after SSA opt ... ')
    udd = UseDefDetector()
    udd.process(scope)

    logger.debug('--------------------------')
    logger.debug('Resolve PHI conditions ... ')
    phi_cond_resolver = PHICondResolver()
    phi_cond_resolver.process(scope)
    logger.debug(str(scope))


def gen_hdl(scope):
    '''
    phase4:
      - HDL generation
    '''
    env.compile_phase = "gen_hdl"

    logger.debug('--------------------------')
    logger.debug('Pre-process HDL generation ... ')
    preprocessor = HDLGenPreprocessor()
    scope.module_info = preprocessor.phase1(scope)

    if not scope.is_testbench():
        vcodegen = VerilogCodeGen(scope)
    else:
        vcodegen = VerilogTestGen(scope)
    logger.debug(str(scope.module_info))
    logger.debug('--------------------------')
    logger.debug('HDL generation ... ')
    vcodegen.generate()
    logger.debug('--------------------------')
    logger.debug(vcodegen.result())

    return vcodegen.result()

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
    
