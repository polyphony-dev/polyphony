from collections import defaultdict, namedtuple
from env import env
import logging

class Driver:
    def __init__(self, procs, scopes):
        self.procs = procs
        self.unprocessed_scopes = [None] * len(procs)
        for i in range(len(procs)):
            self.unprocessed_scopes[i] = scopes[:]
        self.updated = False
        self.logger = logging.getLogger() #root logger
        self.codes = {}

    def insert_scope(self, scope):
        for i in range(len(self.procs)):
            self.unprocessed_scopes[i].append(scope)
            self.unprocessed_scopes[i].sort(key=lambda s: s.order)
        self.updated = True
        
    def process_one(self, proc, scope):
        self.logger.addHandler(env.logfiles[scope])
        self.logger.debug('--------------------------')
        self.logger.debug(str(proc.__name__) + ':' + scope.name)
        proc(self, scope)
        self.logger.removeHandler(env.logfiles[scope])
        
    def run(self):
        while True:
            for i, p in enumerate(self.procs):
                scopes = self.unprocessed_scopes[i][::-1]
                for s in scopes:
                    self.process_one(p, s)
                    self.unprocessed_scopes[i].remove(s)
                if self.updated:
                    self.updated = False
                    break
            else:
                break

    def set_result(self, scope, code):
        self.codes[scope] = code

    def result(self, scope):
        return self.codes[scope]

class TestScope:
    def __init__(self, name, order):
        self.name = name
        self.order = order
    
if __name__ == '__main__':
    def proc_1(driver, scope):
        print('proc1 ' + scope.name)
    def proc_2(driver, scope):
        print('proc2 ' + scope.name)
        if scope.name == 's2':
            driver.insert_scope(TestScope('s2+', 2))
    def proc_3(driver, scope):
        print('proc3 ' + scope.name)
    procs = [proc_1, proc_2, proc_3]
    scopes = [TestScope('s1', 1), TestScope('s2', 2), TestScope('s3',3)]
    driver = Driver(procs, scopes)
    driver.run()
