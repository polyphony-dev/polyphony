#Writing to 'o_q' is conflicted in a pipeline
from polyphony import rule
from polyphony import module
from polyphony.io import Queue
from polyphony import is_worker_running


@module
class io_pipeline_write_conflict01:
    def __init__(self):
        self.i_q = Queue(int, 'in')
        self.o_q = Queue(int, 'out')
        self.append_worker(self.w, self.i_q, self.o_q)

    def w(self, i_q, o_q):
        with rule(scheduling='pipeline'):
            while is_worker_running():
                v = i_q.rd()
                o_q.wr(v)
                o_q.wr(v)


m = io_pipeline_write_conflict01()
