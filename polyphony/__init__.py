__all__ = [
    'testbench',
    'top',
]

def testbench(func):
    return func


class TopDecorator:
    def __init__(self):
        self.top_instance = None
        self.handlers = set()

    def __call__(self, cls):
        def _top_decorator(*args, **kwargs):
            self.top_instance = cls(*args, **kwargs)
            self.top_instance.run = self._top_run
            return self.top_instance
        _top_decorator.__dict__ = cls.__dict__.copy()
        return _top_decorator

    def _top_run(self, cycle):
        for i in range(cycle):
            for th in self.handlers:
                method = getattr(self.top_instance, th.__name__, None)
                assert method
                method()

    def thread(self, func):
        qualname = func.__qualname__.split('.')
        if len(qualname) > 2:
            raise RuntimeError("\'@top.thread\' can only specify to a method of the global \'@top\' class")
        self.handlers.add(func)
        return func

top = TopDecorator()
