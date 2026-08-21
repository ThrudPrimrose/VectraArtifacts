/* DaCe AUTO-GENERATED FILE. DO NOT MODIFY */
#include <dace/dace.h>
#include "../../include/hash.h"

struct s352_d_single_s352_d_single_state_t {

};

void __program_s352_d_single_s352_d_single_internal(s352_d_single_s352_d_single_state_t*__state, double * __restrict__ a, double * __restrict__ b, double * __restrict__ c, int LEN_1D)
{
    double dot;
    int64_t i;

    {

        {
            double __out;

            ///////////////////
            // Tasklet code (assign_9_4)
            __out = 0.0;
            ///////////////////

            dot = __out;
        }

    }
    {

        {
            double __out;

            ///////////////////
            // Tasklet code (assign_10_4)
            __out = 0.0;
            ///////////////////

            dot = __out;
        }

    }

    double dot0 = 0.0, dot1 = 0.0, dot2 = 0.0, dot3 = 0.0, dot4 = 0.0;

    for (i = 0; (i < (LEN_1D - 4)); i = (i + 5)) {
        dot0 += a[i]   * b[i];
        dot1 += a[i+1] * b[i+1];
        dot2 += a[i+2] * b[i+2];
        dot3 += a[i+3] * b[i+3];
        dot4 += a[i+4] * b[i+4];
    }
    dot = dot0 + dot1 + dot2 + dot3 + dot4;
    {

        {
            double __inp = dot;
            double __out;

            ///////////////////
            // Tasklet code (assign_19_4)
            __out = __inp;
            ///////////////////

            c[0] = __out;
        }

    }
}

DACE_EXPORTED void __program_s352_d_single_s352_d_single(s352_d_single_s352_d_single_state_t *__state, double * __restrict__ a, double * __restrict__ b, double * __restrict__ c, int LEN_1D)
{
    __program_s352_d_single_s352_d_single_internal(__state, a, b, c, LEN_1D);
}

DACE_EXPORTED s352_d_single_s352_d_single_state_t *__dace_init_s352_d_single_s352_d_single(int LEN_1D)
{

    int __result = 0;
    s352_d_single_s352_d_single_state_t *__state = new s352_d_single_s352_d_single_state_t;

    if (__result) {
        delete __state;
        return nullptr;
    }

    return __state;
}

DACE_EXPORTED int __dace_exit_s352_d_single_s352_d_single(s352_d_single_s352_d_single_state_t *__state)
{

    int __err = 0;
    delete __state;
    return __err;
}
