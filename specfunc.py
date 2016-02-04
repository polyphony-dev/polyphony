from collections import defaultdict
from symbol import function_name
from scope import Scope
from irvisitor import IRVisitor
from varreplacer import VarReplacer
from memref import MemRefNode
from env import env
from ir import CONST, TEMP, ARRAY, MOVE
from usedef import UseDefDetector
from type import Type
import pdb
import logging
logger = logging.getLogger()

class SpecializedFunctionMaker:
    def __init__(self):
        pass

    def process_all(self):
        scopes = Scope.get_scopes(bottom_up=False)
        calls = defaultdict(set)
        collector = CallCollector(calls)
        using_scopes = set()
        for s in scopes:
            if s.is_testbench():
                using_scopes.add(s)
            collector.process(s)

        new_scopes = []

        for (caller, callee), calls in sorted(calls.items()):
            if caller.is_testbench():
                using_scopes.add(callee)
                continue
            using_scopes.add(caller)

            for call in calls:
                binding = []
                for i, arg in enumerate(call.args):
                    if isinstance(arg, CONST):
                        binding.append((self.bind_val, i, arg.value))
                    elif isinstance(arg, TEMP) and Type.is_list(arg.sym.typ):
                        memnode = Type.extra(arg.sym.typ)
                        if not memnode.is_writable():
                            binding.append((self.bind_rom, i, memnode))
                if binding:
                    descs = '_'.join([self.clone_param_desc(callee, i, a) for _, i, a in binding])
                    new_scope_name = callee.name + '_' + descs
                    if new_scope_name in env.scopes:
                        new_scope = env.scopes[new_scope_name]
                    else:
                        new_scope = callee.clone(descs)
                        udd = UseDefDetector()
                        udd.process(new_scope)
                        for f, i, a in binding:
                            f(new_scope, i, a)
                        for _, i, _ in reversed(binding):
                            new_scope.params.pop(i)
                        new_scopes.append(new_scope)
                        logger.debug('SPECIALIZE ' + new_scope.name)
                    #update CALL target to specialized new_scope
                    fsym = caller.gen_sym('!' + new_scope.orig_name)
                    call.func = TEMP(fsym, call.func.ctx)
                    call.func_scope = new_scope
                    ret_t = call.func_scope.return_type
                    call.func.sym.set_type(('func', ret_t, tuple([param.sym.typ for param in call.func_scope.params])))
                    for _, i, _ in reversed(binding):
                        call.args.pop(i)

                    using_scopes.add(new_scope)
                else:
                    using_scopes.add(callee)
        #remove unused scopes
        for unused in set(scopes).difference(using_scopes):
            logger.debug('REMOVE ' + unused.name)
            env.remove_scope(unused)

        return new_scopes

    @staticmethod
    def clone_param_desc(scope, i, a):
        p, _, _ = scope.params[i]
        if isinstance(a, MemRefNode):
            astr = a.sym.hdl_name()
        else:
            astr = str(a)
        return '{}{}'.format(p.hdl_name(), astr)


    def bind_val(self, scope, i, value):
        replaces = VarReplacer.replace_uses(TEMP(scope.params[i][0], 'Load'), CONST(value), scope.usedef)


    def bind_rom(self, scope, i, memnode):
        root = env.memref_graph.get_single_root(memnode)
        assert root.initstm and isinstance(root.initstm, MOVE) and isinstance(root.initstm.src, ARRAY)
        replaces = VarReplacer.replace_uses(TEMP(scope.params[i][0], 'Load'), root.initstm.src.clone(), scope.usedef)


class CallCollector(IRVisitor):
    def __init__(self, calls):
        super().__init__()
        self.calls = calls

    def visit_CALL(self, ir):
        self.calls[(self.scope, ir.func_scope)].add(ir)

