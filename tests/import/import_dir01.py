import polyphony
import subdir.sub1
from subdir import sub1


def import_dir01():
    return (polyphony.__name__ == 'polyphony' and
            subdir.sub1.__name__ == 'subdir.sub1' and
            sub1.__name__ == 'subdir.sub1')


@polyphony.testbench
def test():
    assert True == import_dir01()
