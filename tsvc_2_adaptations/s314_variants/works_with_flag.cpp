/* DaCe AUTO-GENERATED FILE. DO NOT MODIFY */
#include <dace/dace.h>
#include "../../include/hash.h"

struct s314_d_single_s314_d_single_state_t {

};

void __program_s314_d_single_s314_d_single_internal(s314_d_single_s314_d_single_state_t*__state, double * __restrict__ a, double * __restrict__ result, int LEN_1D)
{
    double x;
    int64_t i;
    double a_index;
    bool __tmp0;

    {


        dace::CopyND<double, 1, false, 1>::template ConstDst<1>::Copy(
        a, &x, 1);

    }

    double v = x;
    for (i = 1; (i < LEN_1D); i = (i + 1)) {
        
        a_index = a[i];

        __tmp0 = (a_index > v);

        if (__tmp0) {
            {
                double x_0;


                dace::CopyND<double, 1, false, 1>::template ConstDst<1>::Copy(
                a + i, &x_0, 1);
                {
                    double __inp = x_0;
                    double __out;

                    ///////////////////
                    // Tasklet code (assign_12_12)
                    __out = __inp;
                    ///////////////////

                    v = __out;
                }

            }
        }


    }

    x = v;

    {

        {
            double __inp = x;
            double __out;

            ///////////////////
            // Tasklet code (assign_13_4)
            __out = __inp;
            ///////////////////

            result[0] = __out;
        }

    }
}

DACE_EXPORTED void __program_s314_d_single_s314_d_single(s314_d_single_s314_d_single_state_t *__state, double * __restrict__ a, double * __restrict__ result, int LEN_1D)
{
    __program_s314_d_single_s314_d_single_internal(__state, a, result, LEN_1D);
}

DACE_EXPORTED s314_d_single_s314_d_single_state_t *__dace_init_s314_d_single_s314_d_single(int LEN_1D)
{

    int __result = 0;
    s314_d_single_s314_d_single_state_t *__state = new s314_d_single_s314_d_single_state_t;

    if (__result) {
        delete __state;
        return nullptr;
    }

    return __state;
}

DACE_EXPORTED int __dace_exit_s314_d_single_s314_d_single(s314_d_single_s314_d_single_state_t *__state)
{

    int __err = 0;
    delete __state;
    return __err;
}
