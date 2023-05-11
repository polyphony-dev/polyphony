import inspect
import sys
from .ir.scope import Scope
from .common.env import env
import logging


class Driver(object):
    def __init__(self, procs, scopes, options, stage_offset=0):
        self.procs = procs
        self.scopes = scopes[:]
        self.disable_scopes = []
        self.options = options
        self.stage_offset = stage_offset
        self.logger = logging.getLogger()  # root logger

    def insert_scope(self, scope):
        self.scopes.append(scope)

    def remove_scope(self, scope):
        if scope in self.scopes:
            self.scopes.remove(scope)
        if scope in self.disable_scopes:
            self.disable_scopes.remove(scope)

    def enable_scope(self, scope):
        if scope in self.disable_scopes:
            self.scopes.append(scope)
            self.disable_scopes.remove(scope)
        else:
            assert scope in self.scopes

    def disable_scope(self, scope):
        if scope in self.scopes:
            self.disable_scopes.append(scope)
            self.scopes.remove(scope)
        else:
            assert scope in self.disable_scopes

    def get_scopes(self, bottom_up=True, with_global=False, with_class=False, with_lib=False):
        scopes = Scope.get_scopes(bottom_up, with_global, with_class, with_lib)
        return [s for s in scopes if s in self.scopes]

    def all_scopes(self):
        return self.scopes + self.disable_scopes

    def start_logging(self, stage, proc, scope):
        if env.dev_debug_mode:
            if not scope.is_lib() and not scope.is_inlinelib():
                self.logger.addHandler(env.scope_log_handler(scope))
            self.logger.addHandler(env.process_log_handler(stage, proc))
        self.logger.debug('--------------------------')
        self.logger.debug(str(proc.__name__) + ':' + scope.name)

    def end_logging(self, stage, proc, scope):
        if env.dev_debug_mode:
            if not scope.is_lib() and not scope.is_inlinelib():
                self.logger.removeHandler(env.scope_log_handler(scope))
            self.logger.removeHandler(env.process_log_handler(stage, proc))

    def run(self, title):
        while True:
            for i, proc in enumerate(self.procs):
                if env.dev_debug_mode:
                    print_progress(title, proc, (i + 1) * 100 // len(self.procs))

                stage = self.stage_offset + i
                Scope.reorder_scopes()
                self.scopes.sort(key=lambda s: s.order)
                scopes = self.scopes[:]

                if 'scope' not in inspect.signature(proc).parameters:
                    for s in scopes:
                        self.start_logging(stage, proc, s)
                    proc(self)
                    for s in scopes:
                        self.end_logging(stage, proc, s)
                else:
                    for s in reversed(scopes):
                        self.start_logging(stage, proc, s)
                        proc(self, s)
                        self.end_logging(stage, proc, s)
            else:
                break


def print_progress(title, proc, percent):
    i = percent // 4
    sys.stdout.write('\r')
    sys.stdout.write('{}: [{:<25}] {}% ... {:<24}'.format(title, '=' * i, percent, proc.__name__))
    sys.stdout.flush()
    if percent == 100:
        print('')
