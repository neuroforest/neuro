from lark import Transformer


class NQLTransformer(Transformer):
    @staticmethod
    def properties(items):
        if len(items) == 0:
            return dict()
        else:
            return dict(items)

    @staticmethod
    def pair(items):
        key = str(items[0])
        val = str(items[1]).strip('"')
        return key, val
