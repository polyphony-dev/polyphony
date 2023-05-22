from polyphony import testbench

def sort(d:list, start):
    flag = 0
    for i in range(start, len(d)-1, 2):
        if d[i] > d[i+1]:
            tmp = d[i]
            d[i] = d[i+1]
            d[i+1] = tmp
            flag = 1
    return flag

def odd_even_sort():
    data = [12, 8, 4, 16, 3, 10, 9, 13, 7, 6, 14, 15, 5, 11, 2, 1]

    flag = 1
    while flag:
        flag = 0
        flag |= sort(data, 0)
        flag |= sort(data, 1)
    for d in data:
        print(d)

    for i in range(1, 16):
        assert data[i-1] < data[i]

@testbench
def test():
    odd_even_sort()
    
test()
