/* Variant C: same fix as A, plus explicit vectorization pragmas on top --
 * tests whether GCC/Clang need an explicit nudge even once the reduction is
 * a clean, canonical idiom (rather than the pragma being load-bearing on its
 * own -- it isn't, on a badly-shaped loop).
 */
#include <dace/dace.h>
#include "../../include/hash.h"

struct s313_d_single_s313_d_single_state_t {

};

void __program_s313_d_single_s313_d_single_internal(s313_d_single_s313_d_single_state_t*__state, double * __restrict__ a, double * __restrict__ b, double * __restrict__ dot, int LEN_1D)
{
    int64_t i;

    dot[0] = 0.0;

    double dot_slice_plus_a_slice_b_slice = dot[0];
#pragma omp simd reduction(+:dot_slice_plus_a_slice_b_slice)
    for (i = 0; (i < LEN_1D); i = (i + 1)) {
        double a_index = a[i];
        double b_index = b[i];
        double a_slice_times_b_slice = a_index * b_index;
        dot_slice_plus_a_slice_b_slice = dot_slice_plus_a_slice_b_slice + a_slice_times_b_slice;
    }

    dot[0] = dot_slice_plus_a_slice_b_slice;
}

DACE_EXPORTED void __program_s313_d_single_s313_d_single(s313_d_single_s313_d_single_state_t *__state, double * __restrict__ a, double * __restrict__ b, double * __restrict__ dot, int LEN_1D)
{
    __program_s313_d_single_s313_d_single_internal(__state, a, b, dot, LEN_1D);
}

DACE_EXPORTED s313_d_single_s313_d_single_state_t *__dace_init_s313_d_single_s313_d_single(int LEN_1D)
{

    int __result = 0;
    s313_d_single_s313_d_single_state_t *__state = new s313_d_single_s313_d_single_state_t;

    if (__result) {
        delete __state;
        return nullptr;
    }

    return __state;
}

DACE_EXPORTED int __dace_exit_s313_d_single_s313_d_single(s313_d_single_s313_d_single_state_t *__state)
{

    int __err = 0;
    delete __state;
    return __err;
}
