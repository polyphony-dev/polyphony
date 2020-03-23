import unittest
import types
from polyphony.compiler.__main__ import setup, compile, compile_plan
from polyphony.compiler.common import src_texts
from polyphony.compiler.env import env


class CompilerTestCase(unittest.TestCase):
    def setUp(self, hook=None, order=0, before=False):
        options = types.SimpleNamespace()
        options.output_name = ''
        options.output_dir = ''
        options.verbose_level = 0
        options.quiet_level = 0
        options.debug_mode = True
        options.verilog_dump = False
        options.verilog_monitor = False
        options.config = None
        self.file_name = 'dummy'
        setup(self.file_name, options)
        plan = compile_plan()
        if hook:
            count = 0
            for idx, p in enumerate(plan):
                if p is hook:
                    if count == order:
                        break
                    count += 1
            else:
                assert False
            if before:
                self.plan = plan[:idx]
            else:
                self.plan = plan[:idx + 1]
        else:
            self.plan = plan

    def tearDown(self):
        env.destroy()

    def _run(self, src):
        src_texts[self.file_name] = src
        compile(self.plan, src, self.file_name)

    def scope(self, scope_name):
        name = '{}.{}'.format(env.global_scope_name, scope_name)
        self.assertTrue(name in env.scopes)
        return env.scopes[name]

    def find_symbol(self, scope, orig_name, ssa_num=0):
        if ssa_num:
            postfix = f'#{ssa_num}'
        else:
            postfix = f''
        sym = scope.find_sym(orig_name + postfix)
        if sym:
            return sym
        for i in range(100):
            name = f'{orig_name}_inl{i}{postfix}'
            sym = scope.find_sym(name)
            if sym:
                return sym
        return None
