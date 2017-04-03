from enum import Enum


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

    # semantic errors
    REFERENCED_BEFORE_ASSIGN = 200

    ASSERTION_FAILED = 300

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
    CLASS_VAR_MUST_BE_CONST = 810

    # polyphony library restrictions
    MUDULE_MUST_BE_IN_GLOBAL = 900
    MODULE_PORT_MUST_ASSIGN_ONLY_ONCE = 901
    MODULE_FIELD_MUST_ASSIGN_IN_CTOR = 902
    CALL_APPEND_WORKER_IN_CTOR = 903
    CALL_MODULE_METHOD = 904
    UNSUPPORTED_TYPES_IN_FUNC = 905
    WORKER_ARG_MUST_BE_X_TYPE = 906
    PORT_MUST_BE_IN_MODULE = 907
    PORT_PARAM_MUST_BE_CONST = 908

    READING_IS_CONFLICTED = 920
    WRITING_IS_CONFLICTED = 921
    DIRECTION_IS_CONFLICTED = 922
    CANNOT_WAIT_OUTPUT = 923

    # polyphony library warnings
    PORT_IS_NOT_USED = 1000

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

    Errors.LEN_TAKES_ONE_ARG: "len() takes exactly one argument",
    Errors.LEN_TAKES_SEQ_TYPE: "len() takes sequence type argument",
    Errors.IS_NOT_CALLABLE: "'{}' is not callable",
    Errors.IS_NOT_SUBSCRIPTABLE: "'{}' is not subscriptable",

    # semantic errors
    Errors.REFERENCED_BEFORE_ASSIGN: "local variable '{}' referenced before assignment",

    Errors.ASSERTION_FAILED: "The expression of assert always evaluates to False",

    # polyphony language restrictions
    Errors.UNSUPPORTED_LETERAL_TYPE: "Unsupported literal type {}",
    Errors.UNSUPPORTED_BINARY_OPERAND_TYPE: "Unsupported operand type(s) for {}: {} and {}",
    Errors.SEQ_ITEM_MUST_BE_INT: "Type of sequence item must be int, not {}",
    Errors.SEQ_MULTIPLIER_MUST_BE_CONST: "Type of sequence multiplier must be constant",
    Errors.UNSUPPORTED_OPERATOR: "Unsupported operator {}",
    Errors.SEQ_CAPACITY_OVERFLOWED: "Sequence capacity is overflowing",
    Errors.UNSUPPORTED_EXPR: "Unsupported expression",
    Errors.GLOBAL_VAR_MUST_BE_CONST: "A global variable must be a constant value",
    Errors.GLOBAL_OBJECT_CANT_BE_MUTABLE: "Writing to a global object is not allowed",
    Errors.GLOBAL_INSTANCE_IS_NOT_SUPPORTED: "A global instance is not supported",
    Errors.CLASS_VAR_MUST_BE_CONST: "A class variable must be a constant value",

    # polyphony library restrictions
    Errors.MUDULE_MUST_BE_IN_GLOBAL: "the module class must be in the global scope",
    Errors.MODULE_PORT_MUST_ASSIGN_ONLY_ONCE: "Assignment to a module port can only be done once",
    Errors.MODULE_FIELD_MUST_ASSIGN_IN_CTOR: "Assignment to a module field can only at the constructor",
    Errors.CALL_APPEND_WORKER_IN_CTOR: "Calling append_worker method can only at the constructor",
    Errors.CALL_MODULE_METHOD: "Calling a method of the module class can only in the module itself",
    Errors.UNSUPPORTED_TYPES_IN_FUNC: "It is not supported to pass the {} type argument to {}()",
    Errors.WORKER_ARG_MUST_BE_X_TYPE: "The type of Worker argument must be an object of Port or constant, not {}",
    Errors.PORT_MUST_BE_IN_MODULE: "Port object must created in the constructor of the module class",
    Errors.PORT_PARAM_MUST_BE_CONST: "The port class constructor accepts only constants",

    Errors.READING_IS_CONFLICTED: "Reading from '{}' is conflicted",
    Errors.WRITING_IS_CONFLICTED: "Writing to '{}' is conflicted",
    Errors.DIRECTION_IS_CONFLICTED: "Port direction of '{}' is conflicted",
    Errors.CANNOT_WAIT_OUTPUT: "Cannot wait for the output port",

    Errors.PORT_IS_NOT_USED: "Port '{}' is not used at all",
}
