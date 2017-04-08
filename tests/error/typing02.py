#A type hint is conflicted
class C:
    def __init__(self):
        self.a: int = 0

    def func(self):
        self.a: str = '0'
