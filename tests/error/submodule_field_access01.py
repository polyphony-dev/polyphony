#Cannot access internal field 'val' of submodule 'sub'; use Port-based communication instead
# CONFIG {"flatten_modules": false}
from polyphony import module
from polyphony.timing import timed


@timed
@module
class Sub:
    def __init__(self):
        self.val = 0
        self.append_worker(self.run, loop=True)

    def run(self):
        self.val = self.val + 1

    def set_val(self, v):
        self.val = v


@module
class Top:
    def __init__(self):
        self.sub = Sub()
        self.append_worker(self.worker)

    def worker(self):
        self.sub.set_val(99)  # inlined method writes to submodule's internal field


top = Top()
