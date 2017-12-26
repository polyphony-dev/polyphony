import polyphony
import polyphony.io
import polyphony.timing
import polyphony.typing
import sub1


def import01():
    return (polyphony.__name__ == 'polyphony' and
            polyphony.io.__name__ == 'polyphony.io' and
            polyphony.timing.__name__ == 'polyphony.timing' and
            polyphony.typing.__name__ == 'polyphony.typing' and
            sub1.__name__ == 'sub1')


@polyphony.testbench
def test():
    assert True == import01()


test()
