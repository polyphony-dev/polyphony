#polyphony.timing.wait_rising() missing required argument
from polyphony import module
from polyphony.io import Bit
from polyphony.timing import wait_rising


@module
class missing_required_arg03:
    def __init__(self):
        p = Bit()
        self.append_worker(self.w, p)

    def w(self, p):
        wait_rising()


m = missing_required_arg03()
