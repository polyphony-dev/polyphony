from polyphony import testbench


def typing07_a(a:bool, b:bool) -> bool:
    return a and b


def typing07_b(a:bool, b:bool) -> bool:
    return a or b


def typing07_c(a:bool, b:bool) -> bool:
    return a & b


def typing07_d(a:bool, b:bool) -> int:
    return a + b


@testbench
def test():
    assert False == typing07_a(False, False)
    assert False == typing07_a(False, True)
    assert False == typing07_a(True, False)
    assert True == typing07_a(True, True)

    assert False == typing07_b(False, False)
    assert True == typing07_b(False, True)
    assert True == typing07_b(True, False)
    assert True == typing07_b(True, True)

    assert False == typing07_c(False, False)
    assert False == typing07_c(False, True)
    assert False == typing07_c(True, False)
    assert True == typing07_c(True, True)

    assert 0 == typing07_d(False, False)
    assert 1 == typing07_d(False, True)
    assert 1 == typing07_d(True, False)
    assert 2 == typing07_d(True, True)


test()
