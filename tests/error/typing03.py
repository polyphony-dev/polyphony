#A type hint for other than 'self.*' is not supported
class C:
    def __init__(self):
        self.a: int = 0

def func():
    c = C()
    c.a:str = '0'
