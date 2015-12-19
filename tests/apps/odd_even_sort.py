from polyphony import testbench

def even_sort(d:list):
    flag = 0
    for i in range(0, len(d)-1, 2):
        if d[i] > d[i+1]:
            tmp = d[i]
            d[i] = d[i+1]
            d[i+1] = tmp
            flag = 1
    return flag

def odd_sort(d:list):
    flag = 0
    for i in range(1, len(d)-1, 2):
        if d[i] > d[i+1]:
            tmp = d[i]
            d[i] = d[i+1]
            d[i+1] = tmp
            flag = 1
    return flag

def odd_even_sort(data:list):
    flag = 1
    while flag:
        flag = 0
        flag |= even_sort(data)
        flag |= odd_sort(data)
    for d in data:
        print(d)


@testbench
def test():
    data = [12, 8, 4, 16, 3, 10, 9, 13, 7, 6, 14, 15, 5, 11, 2, 1]
    odd_even_sort(data)
    for i in range(1, 16):
        assert data[i-1] < data[i]
test()
