/* MinGW-w64 compatibility shim: srand48/drand48/feenableexcept are glibc/POSIX
   extensions not provided by MinGW's runtime. Implements the standard
   48-bit rand48 LCG algorithm (matches glibc semantics) and a no-op
   feenableexcept (FP exception trapping is a debug aid, not needed for
   correctness of the generated cluster). */
#ifndef MINGW_COMPAT_H
#define MINGW_COMPAT_H

#ifdef __MINGW32__
#include <fenv.h>

void srand48(long seedval);
double drand48(void);
static inline int feenableexcept(int excepts) { (void)excepts; return 0; }

#endif /* __MINGW32__ */
#endif /* MINGW_COMPAT_H */
