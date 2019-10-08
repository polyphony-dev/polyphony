#wait_rising() missing required argument 'port'
from polyphony import module
from polyphony.io import Port
from polyphony.timing import wait_rising


@module
class missing_required_arg03:
    def __init__(self):
        p = Port(bool, 'in')
        self.append_worker(self.w, p)

    def w(self, p):
        wait_rising()


m = missing_required_arg03()
