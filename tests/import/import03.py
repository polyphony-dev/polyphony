import polyphony
import sub1 as sub


def import03():
    return sub.__name__ == 'sub1'


@polyphony.testbench
def test():
    assert True == import03()
