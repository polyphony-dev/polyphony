from collections import defaultdict


class DefaultSynthParamSetter(object):
    def __init__(self):
        pass

    testbench_params = {
        'scheduling':'sequential',
        'cycle':'any',
        'ii':1,
    }
    scope_params = {
        'scheduling':'parallel',
        'cycle':'minimum',
        'ii':-1,
    }

    def process(self, scope):
        for k, v in scope.synth_params.items():
            if not v:
                if scope.is_testbench():
                    scope.synth_params[k] = self.testbench_params[k]
                else:
                    scope.synth_params[k] = self.scope_params[k]

        for b in scope.traverse_blocks():
            for k, v in b.synth_params.items():
                if not v:
                    b.synth_params[k] = scope.synth_params[k]


def make_synth_params():
    di = defaultdict(str)
    di['scheduling'] = ''
    di['cycle'] = ''
    di['ii'] = 0
    return di


def merge_synth_params(dst_params, src_params):
    for k, v in dst_params.items():
        if not v:
            dst_params[k] = src_params[k]
