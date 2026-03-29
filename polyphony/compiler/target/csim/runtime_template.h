#ifndef POLYPHONY_CSIM_RUNTIME_H
#define POLYPHONY_CSIM_RUNTIME_H

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

static inline int64_t mask(int64_t v, int w) {
    if (w >= 64) return v;
    return v & ((1LL << w) - 1);
}

static inline int64_t sext(int64_t v, int w) {
    if (w >= 64) return v;
    int64_t m = 1LL << (w - 1);
    return (v ^ m) - m;
}

/* Python-compatible floor division (rounds toward -inf) */
static inline int64_t floordiv(int64_t a, int64_t b) {
    if (b == 0) return 0;
    int64_t q = a / b;
    int64_t r = a % b;
    if ((r != 0) && ((r ^ b) < 0)) q--;
    return q;
}

/* Unsigned floor division (truncating division on non-negative values) */
static inline int64_t ufloordiv(int64_t a, int64_t b) {
    if (b == 0) return 0;
    return (int64_t)((uint64_t)a / (uint64_t)b);
}

/* Signed modulo */
static inline int64_t smod(int64_t a, int64_t b) {
    if (b == 0) return 0;
    return a % b;
}

/* Unsigned modulo */
static inline int64_t umod(int64_t a, int64_t b) {
    if (b == 0) return 0;
    return (int64_t)((uint64_t)a % (uint64_t)b);
}

#endif
