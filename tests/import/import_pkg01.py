import polyphony
import subpkg as sp


def import_pkg01():
    return (sp.__name__ == 'subpkg' and
            sp.sub1.__name__ == 'subpkg.sub1')


@polyphony.testbench
def test():
    assert True == import_pkg01()
