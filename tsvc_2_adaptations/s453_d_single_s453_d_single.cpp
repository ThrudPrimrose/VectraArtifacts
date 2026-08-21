/* DaCe AUTO-GENERATED FILE. DO NOT MODIFY */
#include <dace/dace.h>
#include "../../include/hash.h"

struct s453_d_single_s453_d_single_state_t {

};

void __program_s453_d_single_s453_d_single_internal(s453_d_single_s453_d_single_state_t*__state, double * __restrict__ a, double * __restrict__ b, int LEN_1D)
{
    double s;
    int64_t i;

    {

        {
            double __out;

            ///////////////////
            // Tasklet code (assign_9_4)
            __out = 0.0;
            ///////////////////

            s = __out;
        }

    }

    for (i = 0; (i < LEN_1D); i = (i + 1)) {
        {
            double s_plus_2_0;
            double b_index;
            double a_slice;

            {
                double __in1 = s;
                double __out;

                ///////////////////
                // Tasklet code (_Add_)
                __out = (__in1 + 2.0);
                ///////////////////

                s_plus_2_0 = __out;
            }
            {
                double __inp = s_plus_2_0;
                double __out;

                ///////////////////
                // Tasklet code (assign_11_8)
                __out = __inp;
                ///////////////////

                s = __out;
            }

            dace::CopyND<double, 1, false, 1>::template ConstDst<1>::Copy(
            b + i, &b_index, 1);
            {
                double __in1 = s;
                double __in2 = b_index;
                double __out;

                ///////////////////
                // Tasklet code (_Mult_)
                __out = (__in1 * __in2);
                ///////////////////

                a_slice = __out;
            }
            {
                double __inp = a_slice;
                double __out;

                ///////////////////
                // Tasklet code (assign_12_8)
                __out = __inp;
                ///////////////////

                a[i] = __out;
            }

        }

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
