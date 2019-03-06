import polyphony
from subdir import sub1 as sub1_
from subdir import sub2 as sub2_


def import_dir02():
    return (sub1_.__name__ == 'subdir.sub1' and
            sub2_.__name__ == 'subdir.sub2')


@polyphony.testbench
def test():
    assert True == import_dir02()


test()
