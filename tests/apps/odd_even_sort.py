from polyphony import testbench

def even_sort(d:list):
    N = 8
    flag = 0
    for i in range(0, N-1, 2):
        if d[i] > d[i+1]:
            tmp = d[i]
            d[i] = d[i+1]
            d[i+1] = tmp
            flag = 1
    return flag

def odd_sort(d:list):
    N = 8
    flag = 0
    for i in range(1, N-1, 2):
        if d[i] > d[i+1]:
            tmp = d[i]
            d[i] = d[i+1]
            d[i+1] = tmp
            flag = 1
    return flag

def odd_even_sort():
    data = [8, 4, 3, 7, 6, 5, 2, 1]
    flag = 1
    while flag:
        flag = 0
        flag |= even_sort(data)
        flag |= odd_sort(data)
        print(data[0])
        print(data[1])
        print(data[2])
        print(data[3])
        print(data[4])
        print(data[5])
        print(data[6])
        print(data[7])
    return 0

@testbench
def test():
    ret = odd_even_sort()

test()
