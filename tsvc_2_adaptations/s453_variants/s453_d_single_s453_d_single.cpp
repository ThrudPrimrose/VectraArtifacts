/* DaCe AUTO-GENERATED FILE. DO NOT MODIFY */
#include <dace/dace.h>
#include "../../include/hash.h"

struct s453_d_single_s453_d_single_state_t {

};

void __program_s453_d_single_s453_d_single_internal(s453_d_single_s453_d_single_state_t*__state, double * __restrict__ a, double * __restrict__ b, int LEN_1D)
{
    double s = 0.0;
  
    s = 0.0;
    for (int i = 0; i < LEN_1D; ++i) {
      s += 2.0;
      a[i] = s * b[i];
    }

}

DACE_EXPORTED void __program_s453_d_single_s453_d_single(s453_d_single_s453_d_single_state_t *__state, double * __restrict__ a, double * __restrict__ b, int LEN_1D)
{
    __program_s453_d_single_s453_d_single_internal(__state, a, b, LEN_1D);
}

DACE_EXPORTED s453_d_single_s453_d_single_state_t *__dace_init_s453_d_single_s453_d_single(int LEN_1D)
{

    int __result = 0;
    s453_d_single_s453_d_single_state_t *__state = new s453_d_single_s453_d_single_state_t;

    if (__result) {
        delete __state;
        return nullptr;
    }

    return __state;
}

DACE_EXPORTED int __dace_exit_s453_d_single_s453_d_single(s453_d_single_s453_d_single_state_t *__state)
{

    int __err = 0;
    delete __state;
    return __err;
}
