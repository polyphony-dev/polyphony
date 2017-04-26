import polyphony
import sub1 as sub


@polyphony.testbench
def test():
    sub.__name__ == 'sub1'


test()
