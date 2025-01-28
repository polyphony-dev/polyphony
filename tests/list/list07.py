from polyphony import testbench

def list07(x):
    a = [1,2,3,4,5,6,7,8]
    b = [0]*12

    def memcpy(a:list, b:list):
        for i in range(0, 8):
            b[i] = a[i]

    def memcheck(a:list, b:list):
        for i in range(0, 8):
            if b[i] != a[i]:
                return False
        return True

    memcpy(a, b)
    return memcheck(a, b)

@testbench
def test():
    assert 1 == list07(0)
