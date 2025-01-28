#Reading from 'i' is conflicted in a pipeline
from polyphony import rule
from polyphony import module
from polyphony import Channel
from polyphony import is_worker_running


@module
class io_pipeline_read_conflict01:
    def __init__(self):
        self.i = Channel(int)
        self.o = Channel(int)
        self.append_worker(self.w, self.i, self.o)

    def w(self, i, o):
        with rule(scheduling='pipeline'):
            while is_worker_running():
                v = i.get()
                v += i.get()
                o.put(v)


m = io_pipeline_read_conflict01()
