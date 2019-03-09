import polyphony
import subpkg.sub1


def import_pkg02():
    return (subpkg.__name__ == 'subpkg' and
            subpkg.sub1.__name__ == 'subpkg.sub1')


@polyphony.testbench
def test():
    assert True == import_pkg02()


test()
