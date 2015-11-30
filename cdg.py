from dominator import DominatorTreeBuilder, DominanceFrontierBuilder

class CDGBuilder:
    def __init__(self):
        pass

    def process(self, scope):
        dt_builder = DominatorTreeBuilder(scope)
        tree = dt_builder.process(post=False)
        tree.dump()

        dt_builder = DominatorTreeBuilder(scope)
        posttree = dt_builder.process(post=True)
        posttree.dump()

