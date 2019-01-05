from enum import Enum


class CompileError(Exception):
    pass


class InterpretError(Exception):
    pass


class Errors(Enum):
    # type errors
    MUST_BE_X_TYPE = 100
    MISSING_REQUIRED_ARG = 101
    MISSING_REQUIRED_ARG_N = 102
    TAKES_TOOMANY_ARGS = 103
    UNKNOWN_ATTRIBUTE = 104
    INCOMPATIBLE_TYPES = 105
    INCOMPATIBLE_RETURN_TYPE = 106
    INCOMPATIBLE_PARAMETER_TYPE = 107
    LEN_TAKES_ONE_ARG = 108
    LEN_TAKES_SEQ_TYPE = 109
    IS_NOT_CALLABLE = 110
    IS_NOT_SUBSCRIPTABLE = 111
    CONFLICT_TYPE_HINT = 112
    UNSUPPORTED_ATTRIBUTE_TYPE_HINT = 113
    UNKNOWN_TYPE_NAME = 114
    MUST_BE_X = 115
    GOT_UNEXPECTED_KWARGS = 116
    UNKNOWN_X_IS_SPECIFIED = 117

    # semantic errors
    REFERENCED_BEFORE_ASSIGN = 200
    UNDEFINED_NAME = 201
    CANNOT_IMPORT = 202

    # polyphony language restrictions
    UNSUPPORTED_LETERAL_TYPE = 800
    UNSUPPORTED_BINARY_OPERAND_TYPE = 801
    SEQ_ITEM_MUST_BE_INT = 802
    SEQ_MULTIPLIER_MUST_BE_CONST = 803
    UNSUPPORTED_OPERATOR = 804
    SEQ_CAPACITY_OVERFLOWED = 805
    UNSUPPORTED_EXPR = 806
    GLOBAL_VAR_MUST_BE_CONST = 807
    GLOBAL_OBJECT_CANT_BE_MUTABLE = 808
    GLOBAL_INSTANCE_IS_NOT_SUPPORTED = 809
    UNSUPPORTED_SYNTAX = 810
    UNSUPPORTED_DEFAULT_SEQ_PARAM = 811
    UNSUPPORTED_DECORATOR = 812
    METHOD_MUST_HAVE_SELF = 813
    REDEFINED_NAME = 814
    LOCAL_CLASS_DEFINITION_NOT_ALLOWED = 815
    USE_OUTSIDE_FOR = 816
    NAME_SCOPE_RESTRICTION = 817
    INVALID_MODULE_OBJECT_ACCESS = 818
    PRINT_TAKES_SCALAR_TYPE = 819

    # polyphony library restrictions
    MUDULE_MUST_BE_IN_GLOBAL = 900
    MODULE_FIELD_MUST_ASSIGN_ONLY_ONCE = 901
    MODULE_FIELD_MUST_ASSIGN_IN_CTOR = 902
    CALL_APPEND_WORKER_IN_CTOR = 903
    CALL_MODULE_METHOD = 904
    UNSUPPORTED_TYPES_IN_FUNC = 905
    MODULE_ARG_MUST_BE_X_TYPE = 906
    WORKER_ARG_MUST_BE_X_TYPE = 907
    PORT_MUST_BE_IN_MODULE = 908
    PORT_PARAM_MUST_BE_CONST = 909
    WORKER_MUST_BE_METHOD_OF_MODULE = 910
    PORT_ACCESS_IS_NOT_ALLOWED = 911
    RESERVED_PORT_NAME = 912
    MODULE_CANNOT_ACCESS_OBJECT = 913

    READING_IS_CONFLICTED = 920
    WRITING_IS_CONFLICTED = 921
    DIRECTION_IS_CONFLICTED = 922
    CANNOT_WAIT_OUTPUT = 923

    PURE_ERROR = 930
    PURE_MUST_BE_GLOBAL = 931
    PURE_ARGS_MUST_BE_CONST = 932
    PURE_IS_DISABLED = 933
    PURE_CTOR_MUST_BE_MODULE = 934
    PURE_RETURN_NO_SAME_TYPE = 935

    RULE_BREAK_IN_PIPELINE_LOOP = 1100
    RULE_CONTINUE_IN_PIPELINE_LOOP = 1101
    RULE_FUNCTION_CANNOT_BE_PIPELINED = 1102
    RULE_PIPELINE_HAS_INNER_LOOP = 1103
    RULE_INVALID_II = 1104
    RULE_READING_PIPELINE_IS_CONFLICTED = 1105
    RULE_WRITING_PIPELINE_IS_CONFLICTED = 1106
    RULE_PIPELINE_CANNNOT_FLATTEN = 1107

    RULE_UNROLL_NESTED_LOOP = 1151
    RULE_UNROLL_UNFIXED_LOOP = 1152
    RULE_UNROLL_CONTROL_BRANCH = 1153
    RULE_UNROLL_UNKNOWN_STEP = 1154
    RULE_UNROLL_VARIABLE_STEP = 1155

    # not supported yet
    WRITING_ALIAS_REGARRAY = 9000

    def __str__(self):
        return ERROR_MESSAGES[self]


ERROR_MESSAGES = {
    # type errors
    Errors.MUST_BE_X_TYPE: "Type of '{}' must be {}, not {}",
    Errors.MISSING_REQUIRED_ARG: "{}() missing required argument",
    Errors.MISSING_REQUIRED_ARG_N: "{}() missing required argument {}",
    Errors.TAKES_TOOMANY_ARGS: "{}() takes {} positional arguments but {} were given",
    Errors.UNKNOWN_ATTRIBUTE: "Unknown attribute name '{}'",
    Errors.INCOMPATIBLE_TYPES: "{} and {} are incompatible types",
    Errors.INCOMPATIBLE_RETURN_TYPE: "Type of return value must be {}, not {}",
    Errors.INCOMPATIBLE_PARAMETER_TYPE: "'{}' is incompatible type as a parameter of {}()",
    Errors.CONFLICT_TYPE_HINT: "A type hint is conflicted",
    Errors.UNSUPPORTED_ATTRIBUTE_TYPE_HINT: "A type hint for other than 'self.*' is not supported",
    Errors.UNKNOWN_TYPE_NAME: "Unknown type name '{}'",
    Errors.MUST_BE_X: "{} is expected",
    Errors.GOT_UNEXPECTED_KWARGS: "{}() got an unexpected keyword argument '{}'",
    Errors.UNKNOWN_X_IS_SPECIFIED: "Unknown {} '{}' is specified",

    Errors.LEN_TAKES_ONE_ARG: "len() takes exactly one argument",
    Errors.LEN_TAKES_SEQ_TYPE: "len() takes sequence type argument",
    Errors.IS_NOT_CALLABLE: "'{}' is not callable",
    Errors.IS_NOT_SUBSCRIPTABLE: "'{}' is not subscriptable",

    # semantic errors
    Errors.REFERENCED_BEFORE_ASSIGN: "local variable '{}' referenced before assignment",
    Errors.UNDEFINED_NAME: "'{}' is not defined",
    Errors.CANNOT_IMPORT: "cannot import name '{}'",

    # polyphony language restrictions
    Errors.UNSUPPORTED_LETERAL_TYPE: "Unsupported literal type {}",
    Errors.UNSUPPORTED_BINARY_OPERAND_TYPE: "Unsupported operand type(s) for {}: {} and {}",
    Errors.SEQ_ITEM_MUST_BE_INT: "Type of sequence item must be int, not {}",
    Errors.SEQ_MULTIPLIER_MUST_BE_CONST: "Type of sequence multiplier must be constant",
    Errors.UNSUPPORTED_OPERATOR: "Unsupported operator {}",
    Errors.SEQ_CAPACITY_OVERFLOWED: "Sequence capacity is overflowing",
    Errors.UNSUPPORTED_EXPR: "Unsupported expression",
    Errors.GLOBAL_VAR_MUST_BE_CONST: "A global or class variable must be a constant value",
    Errors.GLOBAL_OBJECT_CANT_BE_MUTABLE: "Writing to a global object is not allowed",
    Errors.GLOBAL_INSTANCE_IS_NOT_SUPPORTED: "A global instance is not supported",
    Errors.UNSUPPORTED_SYNTAX: "{} is not supported",
    Errors.UNSUPPORTED_DEFAULT_SEQ_PARAM:"cannot set the default value to the sequence type parameter",
    Errors.UNSUPPORTED_DECORATOR: "Unsupported decorator '@{}' is specified",
    Errors.METHOD_MUST_HAVE_SELF: "Class method must have a 'self' parameter",
    Errors.REDEFINED_NAME: "'{}' has been redefined",
    Errors.LOCAL_CLASS_DEFINITION_NOT_ALLOWED: "Local class definition in the function is not allowed",
    Errors.USE_OUTSIDE_FOR: "Cannot use {}() function outside of for statememt",
    Errors.NAME_SCOPE_RESTRICTION: "Using the variable 'i' is restricted by polyphony's name scope rule",
    Errors.INVALID_MODULE_OBJECT_ACCESS: "Invalid access to a module class object",
    Errors.PRINT_TAKES_SCALAR_TYPE: "print() takes only scalar type (e.g. int, str, ...) argument",

    # polyphony library restrictions
    Errors.MUDULE_MUST_BE_IN_GLOBAL: "the module class must be in the global scope",
    Errors.MODULE_FIELD_MUST_ASSIGN_ONLY_ONCE: "Assignment to a module field can only be done once",
    Errors.MODULE_FIELD_MUST_ASSIGN_IN_CTOR: "Assignment to a module field can only at the constructor",
    Errors.CALL_APPEND_WORKER_IN_CTOR: "Calling append_worker method can only at the constructor",
    Errors.CALL_MODULE_METHOD: "Calling a method of the module class can only in the module itself",
    Errors.UNSUPPORTED_TYPES_IN_FUNC: "It is not supported to pass the {} type argument to {}()",
    Errors.MODULE_ARG_MUST_BE_X_TYPE: "The type of @module class argument must be constant, not {}",
    Errors.WORKER_ARG_MUST_BE_X_TYPE: "The type of Worker argument must be an object of Port or constant, not {}",
    Errors.PORT_MUST_BE_IN_MODULE: "Port object must created in the constructor of the module class",
    Errors.PORT_PARAM_MUST_BE_CONST: "The port class constructor accepts only constants",
    Errors.WORKER_MUST_BE_METHOD_OF_MODULE: "The worker must be a method of the module",
    Errors.PORT_ACCESS_IS_NOT_ALLOWED: "'any' port cannot be accessed from outside of the module",
    Errors.RESERVED_PORT_NAME: "The name of Port '{}' is reserved",
    Errors.READING_IS_CONFLICTED: "Reading from '{}' is conflicted",
    Errors.WRITING_IS_CONFLICTED: "Writing to '{}' is conflicted",
    Errors.DIRECTION_IS_CONFLICTED: "Port direction of '{}' is conflicted",
    Errors.CANNOT_WAIT_OUTPUT: "Cannot wait for the output port",
    Errors.MODULE_CANNOT_ACCESS_OBJECT: "The module class cannot access an object",

    Errors.PURE_ERROR: "@pure Python execution is failed",
    Errors.PURE_MUST_BE_GLOBAL: "@pure function must be in the global scope",
    Errors.PURE_ARGS_MUST_BE_CONST: "An argument of @pure function must be constant",
    Errors.PURE_IS_DISABLED: "@pure Python execution is disabled",
    Errors.PURE_CTOR_MUST_BE_MODULE: "Classes other than @module class can not use @pure decorator",
    Errors.PURE_RETURN_NO_SAME_TYPE: "@pure function must return the same type values",

    Errors.RULE_BREAK_IN_PIPELINE_LOOP: "Cannot use 'break' statement in the pipeline loop",
    Errors.RULE_CONTINUE_IN_PIPELINE_LOOP: "Cannot use 'continue' statement in the pipeline loop",
    Errors.RULE_FUNCTION_CANNOT_BE_PIPELINED: "Normal function cannot be pipelined",
    Errors.RULE_PIPELINE_HAS_INNER_LOOP: "Cannot pipelining the loop that has an inner loop",
    Errors.RULE_INVALID_II: "Cannot schedule with ii = {}, you must set ii >= {}",
    Errors.RULE_READING_PIPELINE_IS_CONFLICTED: "Reading from '{}' is conflicted in a pipeline",
    Errors.RULE_WRITING_PIPELINE_IS_CONFLICTED: "Writing to '{}' is conflicted in a pipeline",
    Errors.RULE_PIPELINE_CANNNOT_FLATTEN: "Flattening of multiple inner loops in a pipeline loop is not supported",

    Errors.RULE_UNROLL_NESTED_LOOP: "Cannot unroll nested loop",
    Errors.RULE_UNROLL_UNFIXED_LOOP: "Cannot full unroll unfixed loop",
    Errors.RULE_UNROLL_CONTROL_BRANCH: "Cannot unroll loop that having control branches",
    Errors.RULE_UNROLL_UNKNOWN_STEP: "Cannot find the step value of the loop",
    Errors.RULE_UNROLL_VARIABLE_STEP: "The step value must be a constant",

    Errors.WRITING_ALIAS_REGARRAY: "Writing to alias register array is not supported yet",
}


class Warnings(Enum):
    # warnings
    ASSERTION_FAILED = 100
    EXCEPTION_RAISED = 101

    PORT_IS_NOT_USED = 1000

    RULE_PIPELINE_HAS_MEM_READ_CONFLICT = 1130
    RULE_PIPELINE_HAS_MEM_WRITE_CONFLICT = 1131
    RULE_PIPELINE_HAS_MEM_RW_CONFLICT = 1132
    RULE_PIPELINE_HAS_RW_ACCESS_IN_THE_SAME_RAM = 1133

    def __str__(self):
        return WARNING_MESSAGES[self]


WARNING_MESSAGES = {
    Warnings.ASSERTION_FAILED: "The expression of assert always evaluates to False",
    Warnings.EXCEPTION_RAISED: "An exception occurred while executing the Python interpreter at compile time\n(For more information you can use '--verbose' option)",
    Warnings.PORT_IS_NOT_USED: "Port '{}' is not used at all",
    Warnings.RULE_PIPELINE_HAS_MEM_READ_CONFLICT: "There is a read conflict at '{}' in a pipeline, II will be adjusted",
    Warnings.RULE_PIPELINE_HAS_MEM_WRITE_CONFLICT: "There is a write conflict at '{}' in a pipeline, II will be adjusted",
    Warnings.RULE_PIPELINE_HAS_MEM_RW_CONFLICT: "There is a read/write conflict at '{}' in a pipeline, II will be adjusted",
    Warnings.RULE_PIPELINE_HAS_RW_ACCESS_IN_THE_SAME_RAM: "The pipeline may not work correctly if there is both read and write access to the same memory '{}'"
}
