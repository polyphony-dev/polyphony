import ast

class Type:
    @classmethod
    def from_annotation(cls, ann):
        if isinstance(ann, ast.Name):
            if ann.id == 'int':
                return Type.int_t
            elif ann.id == 'list':
                return Type.list_int_t
        return Type.int_t

    int_t = ('int',)
    list_int_t = ('list', int_t)
    bool_t = ('bool',)
    none_t = ('none',)
