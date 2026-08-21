/* Variant A: minimal fix for the accumulator bug in the hand-edited version.
 * The reduction now genuinely carries in a scalar across iterations -- dot[0]
 * is read once (matching whatever assign_11_4 initialized it to) and written
 * once, never touched inside the loop. This is the classic
 * `sum += a[i]*b[i]` idiom essentially every vectorizer (including GCC's)
 * recognizes without needing to see through memory round-trips.
 */
#include <dace/dace.h>
#include "../../include/hash.h"

struct s313_d_single_s313_d_single_state_t {

};

void __program_s313_d_single_s313_d_single_internal(s313_d_single_s313_d_single_state_t*__state, double * __restrict__ a, double * __restrict__ b, double * __restrict__ dot, int LEN_1D)
{
    int64_t i;

    dot[0]  = 0.0;

    double dot_slice_plus_a_slice_b_slice = dot[0];

    for (i = 0; (i < LEN_1D); i = (i + 1)) {
            
        double a_index;
        double b_index;
        
        dace::CopyND<double, 1, false, 1>::template ConstDst<1>::Copy(
            a + i, &a_index, 1);
            
        dace::CopyND<double, 1, false, 1>::template ConstDst<1>::Copy(
            b + i, &b_index, 1);

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
