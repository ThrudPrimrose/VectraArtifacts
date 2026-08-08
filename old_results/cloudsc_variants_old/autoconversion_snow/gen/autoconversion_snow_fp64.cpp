// npbench-autogen -- generated from autoconversion_snow_numpy.py; edit the numpy reference and regenerate, or delete this line to keep local edits as a hand override.
#define _USE_MATH_DEFINES
#include <chrono>
#include <cstdint>
#include <cmath>
#include <cstring>
#include <complex.h>
#ifdef I
#undef I
#endif
#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif
#ifndef M_E
#define M_E 2.71828182845904523536
#endif
/* ``<complex.h>`` in C++ is deprecated and does not
 * always expose the C99 ``_Complex_I`` macro. Provide
 * a portable fallback using the GCC / Clang compound
 * literal extension -- both compilers accept this in
 * both C and C++ modes. */
#ifndef _Complex_I
#define _Complex_I ((double _Complex){0.0, 1.0})
#endif
/* Complex helpers: g++ does not expose the C99
 * ``cabs / csqrt / cexp / cpow / clog`` family by
 * default. Wrap them via the ``__real__`` / ``__imag__``
 * GCC extensions so the same kernel source compiles
 * cleanly in both gcc and g++. clang follows GCC here.
 * Inline static helpers (instead of macros) so they
 * have a single canonical type signature. */
#ifndef creal
#define creal(z) (__real__ (z))
#endif
#ifndef cimag
#define cimag(z) (__imag__ (z))
#endif
#ifndef cabs
#define cabs(z) sqrt(creal(z)*creal(z) + cimag(z)*cimag(z))
#endif
#ifndef carg
#define carg(z) atan2(cimag(z), creal(z))
#endif
/* ``__npb_make_complex(re, im)`` is the portable
 * constructor (compound-literal in GCC/clang). */
#ifndef __npb_make_complex
#define __npb_make_complex(re, im) ((double _Complex){(re), (im)})
#endif
/* ``cexp(z) = exp(re) * (cos(im) + i*sin(im))``. */
#ifndef cexp
#define cexp(z) __npb_make_complex(exp(creal(z))*cos(cimag(z)), exp(creal(z))*sin(cimag(z)))
#endif
/* ``clog(z) = log(|z|) + i*arg(z)``. */
#ifndef clog
#define clog(z) __npb_make_complex(log(cabs(z)), carg(z))
#endif
/* ``csqrt(z) = exp((1/2) * log(z))`` -- principal branch. */
#ifndef csqrt
#define csqrt(z) cexp(__npb_make_complex(0.5*creal(clog(z)), 0.5*cimag(clog(z))))
#endif
/* ``cpow(z, w) = exp(w * log(z))`` -- general complex pow. */
#ifndef cpow
#define cpow(z, w) cexp(__npb_make_complex(creal(w)*creal(clog(z)) - cimag(w)*cimag(clog(z)), creal(w)*cimag(clog(z)) + cimag(w)*creal(clog(z))))
#endif
/* ``z.conjugate()`` -- portable complex-conjugate scalar
 * helper, mirrors the C-side prelude. */
static inline double _Complex __npb_conj(double _Complex z) {
    return __npb_make_complex(creal(z), -cimag(z));
}
/* Integer power for VLA shape bounds. */
static inline int64_t __npb_int_pow(int64_t base, int64_t exp) {
    int64_t result = 1;
    while (exp > 0) {
        if (exp & 1) result *= base;
        base *= base;
        exp >>= 1;
    }
    return result;
}
/* Use the ternary-form ``max`` / ``min`` (same as the C
 * header) so mixed-type calls like ``max(double, int)``
 * promote the int operand. ``std::max`` from <algorithm>
 * would require both args to share a type. */
#ifndef max
#define max(a, b) (((a) > (b)) ? (a) : (b))
#endif
#ifndef min
#define min(a, b) (((a) < (b)) ? (a) : (b))
#endif
/* Python ``//`` floor-toward-neg-inf semantics for mixed-sign
 * inputs -- C and C++ ``/`` truncate toward zero. The macro
 * matches numpy ``//`` for both languages. */
#ifndef int_floor
#define int_floor(a, b) ((a)/(b) - (((a)%(b)!=0) && (((a)<0)^((b)<0))))
#endif
/* Python ``%`` returns sign of divisor; C/C++ returns sign of
 * dividend. ``python_mod`` bridges the gap. */
#ifndef python_mod
#define python_mod(a, b) (((a) % (b) + (b)) % (b))
#endif

extern "C" {

void autoconversion_snow_fp64(const double *__restrict__ pnice, const double *__restrict__ zicecld, double *__restrict__ zsnowaut, double *__restrict__ zsolqb, const double *__restrict__ ztp1, int64_t KLON, int64_t NCLDQI, int64_t NCLDQS, int64_t laericeauto, double ptsphy, double rlcritsnow, double rnice, double rsnowlin1, double rsnowlin2, double rtt, double zepsec, int64_t *__restrict__ time_ns) {
    auto __t1 = std::chrono::high_resolution_clock::now();
    {
        double zzco;
        double zlcrit;
        for (int64_t jl = 0; jl < KLON; ++jl) {
          zsnowaut[jl] = 0.0;
        }
        for (int64_t jl = 0; jl < KLON; ++jl) {
          if ((ztp1[jl] <= rtt)) {
            if ((zicecld[jl] > zepsec)) {
              zzco = ((ptsphy * rsnowlin1) * exp((rsnowlin2 * (ztp1[jl] - rtt))));
              if ((laericeauto != 0)) {
                zlcrit = rlcritsnow;
                zzco = (zzco * pow((rnice / pnice[jl]), 0.333));
              }
              else {
                zlcrit = rlcritsnow;
              }
              zsnowaut[jl] = (zzco * (1.0 - exp((-pow((zicecld[jl] / zlcrit), 2)))));
              zsolqb[((jl)*(NCLDQS) + ((NCLDQS - 1)))*(NCLDQI) + ((NCLDQI - 1))] = (zsolqb[((jl)*(NCLDQS) + ((NCLDQS - 1)))*(NCLDQI) + ((NCLDQI - 1))] + zsnowaut[jl]);
            }
          }
        }
    }
    auto __t2 = std::chrono::high_resolution_clock::now();
    time_ns[0] = std::chrono::duration_cast<std::chrono::nanoseconds>(
                       __t2 - __t1).count();
}
} // extern "C"
