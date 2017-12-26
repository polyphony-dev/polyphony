'''
Like the Python typing module, this library provides type classes for type hinting.
The following type classes are provided.

    - polyphony.typing.bit
    - polyphony.typing.int<n>
    - polyphony.typing.uint<n>
    - polyphony.typing.List[T]
    - polyphony.typing.List[T][C]  ※C indicates the capacity of the list
    - polyphony.typing.Tuple[T, ...]

The main purpose of polyphony.typing is to specify arbitrary parameters
(bit width, RAM size of the list, etc.) for resources such as register
which is the synthesis result by type hinting for a certain variable.

If you do not specify a type, for example, if it is an int type variable, a default bit width is used.

Type hinting in Polyphony is a feature to generate a resource efficient circuit.
Also, of course, it can be used to detect errors due to type at compile time.
'''

import abc


__all__ = [
    'bit',
    'List',
    'Tuple',
]
__all__ += ['bit' + str(i) for i in range(2, 129)]
__all__ += ['int' + str(i) for i in range(2, 129)]
__all__ += ['uint' + str(i) for i in range(2, 129)]


class GenericMeta(abc.ABCMeta):
    def __getitem__(self, i):
        return self.__class__(self.__name__, self.__bases__, dict(self.__dict__))


class List(list, metaclass=GenericMeta):
    pass


class Tuple(tuple, metaclass=GenericMeta):
    pass


class int_base:
    base_type = int

class bit(int_base): pass
class bit2(int_base): pass
class bit3(int_base): pass
class bit4(int_base): pass
class bit5(int_base): pass
class bit6(int_base): pass
class bit7(int_base): pass
class bit8(int_base): pass
class bit9(int_base): pass
class bit10(int_base): pass
class bit11(int_base): pass
class bit12(int_base): pass
class bit13(int_base): pass
class bit14(int_base): pass
class bit15(int_base): pass
class bit16(int_base): pass
class bit17(int_base): pass
class bit18(int_base): pass
class bit19(int_base): pass
class bit20(int_base): pass
class bit21(int_base): pass
class bit22(int_base): pass
class bit23(int_base): pass
class bit24(int_base): pass
class bit25(int_base): pass
class bit26(int_base): pass
class bit27(int_base): pass
class bit28(int_base): pass
class bit29(int_base): pass
class bit30(int_base): pass
class bit31(int_base): pass
class bit32(int_base): pass
class bit33(int_base): pass
class bit34(int_base): pass
class bit35(int_base): pass
class bit36(int_base): pass
class bit37(int_base): pass
class bit38(int_base): pass
class bit39(int_base): pass
class bit40(int_base): pass
class bit41(int_base): pass
class bit42(int_base): pass
class bit43(int_base): pass
class bit44(int_base): pass
class bit45(int_base): pass
class bit46(int_base): pass
class bit47(int_base): pass
class bit48(int_base): pass
class bit49(int_base): pass
class bit50(int_base): pass
class bit51(int_base): pass
class bit52(int_base): pass
class bit53(int_base): pass
class bit54(int_base): pass
class bit55(int_base): pass
class bit56(int_base): pass
class bit57(int_base): pass
class bit58(int_base): pass
class bit59(int_base): pass
class bit60(int_base): pass
class bit61(int_base): pass
class bit62(int_base): pass
class bit63(int_base): pass
class bit64(int_base): pass
class bit65(int_base): pass
class bit66(int_base): pass
class bit67(int_base): pass
class bit68(int_base): pass
class bit69(int_base): pass
class bit70(int_base): pass
class bit71(int_base): pass
class bit72(int_base): pass
class bit73(int_base): pass
class bit74(int_base): pass
class bit75(int_base): pass
class bit76(int_base): pass
class bit77(int_base): pass
class bit78(int_base): pass
class bit79(int_base): pass
class bit80(int_base): pass
class bit81(int_base): pass
class bit82(int_base): pass
class bit83(int_base): pass
class bit84(int_base): pass
class bit85(int_base): pass
class bit86(int_base): pass
class bit87(int_base): pass
class bit88(int_base): pass
class bit89(int_base): pass
class bit90(int_base): pass
class bit91(int_base): pass
class bit92(int_base): pass
class bit93(int_base): pass
class bit94(int_base): pass
class bit95(int_base): pass
class bit96(int_base): pass
class bit97(int_base): pass
class bit98(int_base): pass
class bit99(int_base): pass
class bit100(int_base): pass
class bit101(int_base): pass
class bit102(int_base): pass
class bit103(int_base): pass
class bit104(int_base): pass
class bit105(int_base): pass
class bit106(int_base): pass
class bit107(int_base): pass
class bit108(int_base): pass
class bit109(int_base): pass
class bit110(int_base): pass
class bit111(int_base): pass
class bit112(int_base): pass
class bit113(int_base): pass
class bit114(int_base): pass
class bit115(int_base): pass
class bit116(int_base): pass
class bit117(int_base): pass
class bit118(int_base): pass
class bit119(int_base): pass
class bit120(int_base): pass
class bit121(int_base): pass
class bit122(int_base): pass
class bit123(int_base): pass
class bit124(int_base): pass
class bit125(int_base): pass
class bit126(int_base): pass
class bit127(int_base): pass
class bit128(int_base): pass
class bit256(int_base): pass
class bit512(int_base): pass
class bit1024(int_base): pass

class int2(int_base): pass
class int3(int_base): pass
class int4(int_base): pass
class int5(int_base): pass
class int6(int_base): pass
class int7(int_base): pass
class int8(int_base): pass
class int9(int_base): pass
class int10(int_base): pass
class int11(int_base): pass
class int12(int_base): pass
class int13(int_base): pass
class int14(int_base): pass
class int15(int_base): pass
class int16(int_base): pass
class int17(int_base): pass
class int18(int_base): pass
class int19(int_base): pass
class int20(int_base): pass
class int21(int_base): pass
class int22(int_base): pass
class int23(int_base): pass
class int24(int_base): pass
class int25(int_base): pass
class int26(int_base): pass
class int27(int_base): pass
class int28(int_base): pass
class int29(int_base): pass
class int30(int_base): pass
class int31(int_base): pass
class int32(int_base): pass
class int33(int_base): pass
class int34(int_base): pass
class int35(int_base): pass
class int36(int_base): pass
class int37(int_base): pass
class int38(int_base): pass
class int39(int_base): pass
class int40(int_base): pass
class int41(int_base): pass
class int42(int_base): pass
class int43(int_base): pass
class int44(int_base): pass
class int45(int_base): pass
class int46(int_base): pass
class int47(int_base): pass
class int48(int_base): pass
class int49(int_base): pass
class int50(int_base): pass
class int51(int_base): pass
class int52(int_base): pass
class int53(int_base): pass
class int54(int_base): pass
class int55(int_base): pass
class int56(int_base): pass
class int57(int_base): pass
class int58(int_base): pass
class int59(int_base): pass
class int60(int_base): pass
class int61(int_base): pass
class int62(int_base): pass
class int63(int_base): pass
class int64(int_base): pass
class int65(int_base): pass
class int66(int_base): pass
class int67(int_base): pass
class int68(int_base): pass
class int69(int_base): pass
class int70(int_base): pass
class int71(int_base): pass
class int72(int_base): pass
class int73(int_base): pass
class int74(int_base): pass
class int75(int_base): pass
class int76(int_base): pass
class int77(int_base): pass
class int78(int_base): pass
class int79(int_base): pass
class int80(int_base): pass
class int81(int_base): pass
class int82(int_base): pass
class int83(int_base): pass
class int84(int_base): pass
class int85(int_base): pass
class int86(int_base): pass
class int87(int_base): pass
class int88(int_base): pass
class int89(int_base): pass
class int90(int_base): pass
class int91(int_base): pass
class int92(int_base): pass
class int93(int_base): pass
class int94(int_base): pass
class int95(int_base): pass
class int96(int_base): pass
class int97(int_base): pass
class int98(int_base): pass
class int99(int_base): pass
class int100(int_base): pass
class int101(int_base): pass
class int102(int_base): pass
class int103(int_base): pass
class int104(int_base): pass
class int105(int_base): pass
class int106(int_base): pass
class int107(int_base): pass
class int108(int_base): pass
class int109(int_base): pass
class int110(int_base): pass
class int111(int_base): pass
class int112(int_base): pass
class int113(int_base): pass
class int114(int_base): pass
class int115(int_base): pass
class int116(int_base): pass
class int117(int_base): pass
class int118(int_base): pass
class int119(int_base): pass
class int120(int_base): pass
class int121(int_base): pass
class int122(int_base): pass
class int123(int_base): pass
class int124(int_base): pass
class int125(int_base): pass
class int126(int_base): pass
class int127(int_base): pass
class int128(int_base): pass

class uint2(int_base): pass
class uint3(int_base): pass
class uint4(int_base): pass
class uint5(int_base): pass
class uint6(int_base): pass
class uint7(int_base): pass
class uint8(int_base): pass
class uint9(int_base): pass
class uint10(int_base): pass
class uint11(int_base): pass
class uint12(int_base): pass
class uint13(int_base): pass
class uint14(int_base): pass
class uint15(int_base): pass
class uint16(int_base): pass
class uint17(int_base): pass
class uint18(int_base): pass
class uint19(int_base): pass
class uint20(int_base): pass
class uint21(int_base): pass
class uint22(int_base): pass
class uint23(int_base): pass
class uint24(int_base): pass
class uint25(int_base): pass
class uint26(int_base): pass
class uint27(int_base): pass
class uint28(int_base): pass
class uint29(int_base): pass
class uint30(int_base): pass
class uint31(int_base): pass
class uint32(int_base): pass
class uint33(int_base): pass
class uint34(int_base): pass
class uint35(int_base): pass
class uint36(int_base): pass
class uint37(int_base): pass
class uint38(int_base): pass
class uint39(int_base): pass
class uint40(int_base): pass
class uint41(int_base): pass
class uint42(int_base): pass
class uint43(int_base): pass
class uint44(int_base): pass
class uint45(int_base): pass
class uint46(int_base): pass
class uint47(int_base): pass
class uint48(int_base): pass
class uint49(int_base): pass
class uint50(int_base): pass
class uint51(int_base): pass
class uint52(int_base): pass
class uint53(int_base): pass
class uint54(int_base): pass
class uint55(int_base): pass
class uint56(int_base): pass
class uint57(int_base): pass
class uint58(int_base): pass
class uint59(int_base): pass
class uint60(int_base): pass
class uint61(int_base): pass
class uint62(int_base): pass
class uint63(int_base): pass
class uint64(int_base): pass
class uint65(int_base): pass
class uint66(int_base): pass
class uint67(int_base): pass
class uint68(int_base): pass
class uint69(int_base): pass
class uint70(int_base): pass
class uint71(int_base): pass
class uint72(int_base): pass
class uint73(int_base): pass
class uint74(int_base): pass
class uint75(int_base): pass
class uint76(int_base): pass
class uint77(int_base): pass
class uint78(int_base): pass
class uint79(int_base): pass
class uint80(int_base): pass
class uint81(int_base): pass
class uint82(int_base): pass
class uint83(int_base): pass
class uint84(int_base): pass
class uint85(int_base): pass
class uint86(int_base): pass
class uint87(int_base): pass
class uint88(int_base): pass
class uint89(int_base): pass
class uint90(int_base): pass
class uint91(int_base): pass
class uint92(int_base): pass
class uint93(int_base): pass
class uint94(int_base): pass
class uint95(int_base): pass
class uint96(int_base): pass
class uint97(int_base): pass
class uint98(int_base): pass
class uint99(int_base): pass
class uint100(int_base): pass
class uint101(int_base): pass
class uint102(int_base): pass
class uint103(int_base): pass
class uint104(int_base): pass
class uint105(int_base): pass
class uint106(int_base): pass
class uint107(int_base): pass
class uint108(int_base): pass
class uint109(int_base): pass
class uint110(int_base): pass
class uint111(int_base): pass
class uint112(int_base): pass
class uint113(int_base): pass
class uint114(int_base): pass
class uint115(int_base): pass
class uint116(int_base): pass
class uint117(int_base): pass
class uint118(int_base): pass
class uint119(int_base): pass
class uint120(int_base): pass
class uint121(int_base): pass
class uint122(int_base): pass
class uint123(int_base): pass
class uint124(int_base): pass
class uint125(int_base): pass
class uint126(int_base): pass
class uint127(int_base): pass
class uint128(int_base): pass
