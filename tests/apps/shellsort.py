from polyphony import testbench


def shell_sort(alist):
    n = len(alist) // 2
    while n > 0:
        for i in range(n):
            gap_insertion_sort(alist, i, n)
        n = n // 2


def gap_insertion_sort(alist:list, start, gap):
    for i in range(start + gap, len(alist), gap):
        val = alist[i]
        pos = i
        while pos >= gap and alist[pos - gap] > val:
            t = alist[pos - gap]
            alist[pos] = t
            pos -= gap
        alist[pos] = val


@testbench
def test():
    alist = [54, 26, 93, 17, 77, 31, 44, 55, 20]
    shell_sort(alist)
    #gap_insertion_sort(alist, 0, 1)

    for a in alist:
        print(a)
    for i in range(1, 9):
        assert alist[i - 1] < alist[i]


test()

