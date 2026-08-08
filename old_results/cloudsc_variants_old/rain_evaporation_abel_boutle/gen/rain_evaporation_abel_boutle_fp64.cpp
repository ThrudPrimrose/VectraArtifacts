// npbench-autogen -- generated from rain_evaporation_abel_boutle_numpy.py; edit the numpy reference and regenerate, or delete this line to keep local edits as a hand override.
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

void rain_evaporation_abel_boutle_fp64(const double *__restrict__ pap, const double *__restrict__ za, const double *__restrict__ zcovpclr, const double *__restrict__ zcovpmax, double *__restrict__ zcovptot, double *__restrict__ zevap_out, const double *__restrict__ zqsliq, const double *__restrict__ zqx_ncldqv, double *__restrict__ zqxfg_ncldqr, const double *__restrict__ zrho, double *__restrict__ zsolqa, const double *__restrict__ ztp1, int64_t KLON, int64_t NCLDQR, int64_t NCLDQV, int64_t NCLV, double ptsphy, double rcl_cdenom1, double rcl_cdenom2, double rcl_cdenom3, double rcl_const1r, double rcl_const2r, double rcl_const3r, double rcl_const4r, double rcl_fac1, double rcl_fac2, double rcl_ka273, double rcovpmin, double rd, double rdensref, double rprecrhmax, double rtt, double rv, double zepsec, int64_t *__restrict__ time_ns) {
    auto __t1 = std::chrono::high_resolution_clock::now();
    {
        double r2es_local;
        double r3les_local;
        double r4les_local;
        double zzrh;
        double zqe;
        double llo1;
        double zpreclr;
        double zfallcorr;
        double zesatliq;
        double zlambda;
        double zevap_denom;
        double zcorr2;
        double zka;
        double zsubsat;
        double zbeta;
        double zdenom;
        double zdpevap;
        double zevap;
        r2es_local = 611.21;
        r3les_local = 17.502;
        r4les_local = 32.19;
        for (int64_t jl = 0; jl < KLON; ++jl) {
          zevap_out[jl] = 0.0;
        }
        for (int64_t jl = 0; jl < KLON; ++jl) {
          zzrh = (rprecrhmax + (((1.0 - rprecrhmax) * zcovpmax[jl]) / max(zepsec, (1.0 - za[jl]))));
          zzrh = min(max(zzrh, rprecrhmax), 1.0);
          zzrh = min(0.8, zzrh);
          zqe = max(0.0, min(zqx_ncldqv[jl], zqsliq[jl]));
          llo1 = ((zcovpclr[jl] > zepsec) && (zqxfg_ncldqr[jl] > zepsec) && (zqe < (zzrh * zqsliq[jl])));
          if (llo1) {
            zpreclr = (zqxfg_ncldqr[jl] / zcovptot[jl]);
            zfallcorr = pow((rdensref / zrho[jl]), 0.4);
            zesatliq = (((rv / rd) * r2es_local) * exp(((r3les_local * (ztp1[jl] - rtt)) / (ztp1[jl] - r4les_local))));
            zlambda = pow((rcl_fac1 / (zrho[jl] * zpreclr)), rcl_fac2);
            zevap_denom = (((rcl_cdenom1 * zesatliq) - ((rcl_cdenom2 * ztp1[jl]) * zesatliq)) + ((rcl_cdenom3 * pow(ztp1[jl], 3)) * pap[jl]));
            zcorr2 = ((pow((ztp1[jl] / 273.0), 1.5) * 393.0) / (ztp1[jl] + 120.0));
            zka = (rcl_ka273 * zcorr2);
            zsubsat = max(((zzrh * zqsliq[jl]) - zqe), 0.0);
            zbeta = ((((((0.5 / zqsliq[jl]) * pow(ztp1[jl], 2)) * zesatliq) * rcl_const1r) * (zcorr2 / zevap_denom)) * ((0.78 / pow(zlambda, rcl_const4r)) + ((rcl_const2r * pow((zrho[jl] * zfallcorr), 0.5)) / (pow(zcorr2, 0.5) * pow(zlambda, rcl_const3r)))));
            zdenom = (1.0 + (zbeta * ptsphy));
            zdpevap = ((((zcovpclr[jl] * zbeta) * ptsphy) * zsubsat) / zdenom);
            zevap = min(zdpevap, zqxfg_ncldqr[jl]);
            zevap_out[jl] = zevap;
            zsolqa[((jl)*(NCLV) + ((NCLDQV - 1)))*(NCLV) + ((NCLDQR - 1))] = (zsolqa[((jl)*(NCLV) + ((NCLDQV - 1)))*(NCLV) + ((NCLDQR - 1))] + zevap);
            zsolqa[((jl)*(NCLV) + ((NCLDQR - 1)))*(NCLV) + ((NCLDQV - 1))] = (zsolqa[((jl)*(NCLV) + ((NCLDQR - 1)))*(NCLV) + ((NCLDQV - 1))] - zevap);
            zcovptot[jl] = max(rcovpmin, (zcovptot[jl] - max(0.0, (((zcovptot[jl] - za[jl]) * zevap) / zqxfg_ncldqr[jl]))));
            zqxfg_ncldqr[jl] = (zqxfg_ncldqr[jl] - zevap);
          }
        }
    }
    auto __t2 = std::chrono::high_resolution_clock::now();
    time_ns[0] = std::chrono::duration_cast<std::chrono::nanoseconds>(
                       __t2 - __t1).count();
}
} // extern "C"
