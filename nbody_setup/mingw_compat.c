/* MinGW-w64 compatibility shim: implements srand48/drand48 using the
   standard 48-bit rand48 linear congruential generator (same recurrence
   glibc uses: X_{n+1} = (a*X_n + c) mod 2^48, a=0x5DEECE66D, c=0xB). */
#ifdef __MINGW32__
#include <stdint.h>

static uint64_t rand48_state = 0x1234ABCDULL;

static const uint64_t RAND48_A = 0x5DEECE66DULL;
static const uint64_t RAND48_C = 0xBULL;
static const uint64_t RAND48_MASK = (1ULL << 48) - 1;

void srand48(long seedval) {
    rand48_state = (((uint64_t)(uint32_t)seedval) << 16 | 0x330E) & RAND48_MASK;
}

double drand48(void) {
    rand48_state = (RAND48_A * rand48_state + RAND48_C) & RAND48_MASK;
    return (double)rand48_state / (double)(1ULL << 48);
}
#endif /* __MINGW32__ */
