import polyphony
from polyphony import io as io_
from polyphony import timing as ti_
from polyphony import typing as ty_


def import02():
    return (io_.__name__ == 'polyphony.io' and
            ti_.__name__ == 'polyphony.timing' and
            ty_.__name__ == 'polyphony.typing')


@polyphony.testbench
def test():
    assert True == import02()
