/* Variant B: same fix as A, but with 4 explicit partial-sum accumulators,
 * manually "pre-unrolled" the way a vectorizer wants to see a reduction --
 * each accumulator maps naturally onto one SIMD lane, combined once at the
 * end. Sometimes pushes a vectorizer that's on the fence about reassociating
 * a single scalar accumulator (interleaving/unrolling cost-model hesitation)
 * into committing, since the reassociation is now explicit in the source
 * rather than something it has to introduce itself.
 */
#include <dace/dace.h>
#include "../../include/hash.h"

struct s313_d_single_s313_d_single_state_t {

};

void __program_s313_d_single_s313_d_single_internal(s313_d_single_s313_d_single_state_t*__state, double * __restrict__ a, double * __restrict__ b, double * __restrict__ dot, int LEN_1D)
{
    int64_t i;

    dot[0] = 0.0;

    double sum0 = 0.0, sum1 = 0.0, sum2 = 0.0, sum3 = 0.0;
    int64_t n = LEN_1D;
    int64_t n4 = n - (n % 4);
    for (i = 0; i < n4; i += 4) {
        sum0 = sum0 + a[i]     * b[i];
        sum1 = sum1 + a[i + 1] * b[i + 1];
        sum2 = sum2 + a[i + 2] * b[i + 2];
        sum3 = sum3 + a[i + 3] * b[i + 3];
    }
    double dot_slice_plus_a_slice_b_slice = (sum0 + sum1) + (sum2 + sum3);
    for (; i < n; i = i + 1) {
        dot_slice_plus_a_slice_b_slice = dot_slice_plus_a_slice_b_slice + a[i] * b[i];
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
