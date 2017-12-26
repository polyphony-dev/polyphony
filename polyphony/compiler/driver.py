import inspect
import sys
from .scope import Scope
from .env import env
import logging


class Driver(object):
    def __init__(self, procs, scopes):
        self.procs = procs
        self.scopes = scopes[:]
        self.disable_scopes = []
        self.logger = logging.getLogger()  # root logger
        self.codes = {}

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

    def start_logging(self, proc, scope):
        if env.dev_debug_mode and scope in env.logfiles:
            self.logger.addHandler(env.logfiles[scope])
        self.logger.debug('--------------------------')
        self.logger.debug(str(proc.__name__) + ':' + scope.name)

    def end_logging(self, proc, scope):
        if env.dev_debug_mode and scope in env.logfiles:
            self.logger.removeHandler(env.logfiles[scope])

    def run(self):
        while True:
            for i, proc in enumerate(self.procs):
                if env.dev_debug_mode:
                    print_progress(proc, (i + 1) * 100 // len(self.procs))

                self.stage = i
                Scope.reorder_scopes()
                self.scopes.sort(key=lambda s: s.order)
                scopes = self.scopes[:]

                if 'scope' not in inspect.signature(proc).parameters:
                    for s in scopes:
                        self.start_logging(proc, s)
                    proc(self)
                    for s in scopes:
                        self.end_logging(proc, s)
                else:
                    for s in reversed(scopes):
                        self.start_logging(proc, s)
                        proc(self, s)
                        self.end_logging(proc, s)
            else:
                break

    def set_result(self, scope, code):
        self.codes[scope] = code

    def result(self, scope):
        if scope in self.codes:
            return self.codes[scope]
        return None


def print_progress(proc, percent):
    i = percent // 4
    sys.stdout.write('\r')
    sys.stdout.write('Compiling: [{:<25}] {}% ... {:<24}'.format('=' * i, percent, proc.__name__))
    sys.stdout.flush()
    if percent == 100:
        print('')
