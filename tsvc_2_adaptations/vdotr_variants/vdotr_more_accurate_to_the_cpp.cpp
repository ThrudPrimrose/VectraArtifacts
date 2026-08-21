/* DaCe AUTO-GENERATED FILE. DO NOT MODIFY */
#include <dace/dace.h>
#include "../../include/hash.h"

struct vdotr_d_single_vdotr_d_single_state_t {

};

void __program_vdotr_d_single_vdotr_d_single_internal(vdotr_d_single_vdotr_d_single_state_t*__state, double * __restrict__ a, double * __restrict__ b, double * __restrict__ dot_out, int LEN_1D)
{
    int64_t i;

    {

        {
            double __out;

            ///////////////////
            // Tasklet code (assign_11_4)
            __out = 0.0;
            ///////////////////

            dot_out[0] = __out;
        }

    }
    {

        {
            double __out;

            ///////////////////
            // Tasklet code (assign_12_4)
            __out = 0.0;
            ///////////////////

            dot_out[0] = __out;
        }

    }

    double dot_out_slice_plus_a_slice_b_slice;
    for (i = 0; (i < LEN_1D); i = (i + 1)) {
        {
            double a_index;
            double b_index;
            double a_slice_times_b_slice;

            
            dace::CopyND<double, 1, false, 1>::template ConstDst<1>::Copy(
            a + i, &a_index, 1);

            dace::CopyND<double, 1, false, 1>::template ConstDst<1>::Copy(
            b + i, &b_index, 1);
            {
                double __in1 = a_index;
                double __in2 = b_index;
                double __out;

                ///////////////////
                // Tasklet code (_Mult_)
                __out = (__in1 * __in2);
                ///////////////////

                a_slice_times_b_slice = __out;
            }
            {
                double __in2 = a_slice_times_b_slice;
                double __in1 = dot_out_slice_plus_a_slice_b_slice;
                double __out;

                ///////////////////
                // Tasklet code (_Add_)
                __out = (__in1 + __in2);
                ///////////////////

                dot_out_slice_plus_a_slice_b_slice = __out;
            }
            
        }
        
    }

    {
        double __inp = dot_out_slice_plus_a_slice_b_slice;
        double __out;

        ///////////////////
        // Tasklet code (assign_14_8)
        __out = __inp;
        ///////////////////

        dot_out[0] = __out;
    }

}

DACE_EXPORTED void __program_vdotr_d_single_vdotr_d_single(vdotr_d_single_vdotr_d_single_state_t *__state, double * __restrict__ a, double * __restrict__ b, double * __restrict__ dot_out, int LEN_1D)
{
    __program_vdotr_d_single_vdotr_d_single_internal(__state, a, b, dot_out, LEN_1D);
}

DACE_EXPORTED vdotr_d_single_vdotr_d_single_state_t *__dace_init_vdotr_d_single_vdotr_d_single(int LEN_1D)
{

    int __result = 0;
    vdotr_d_single_vdotr_d_single_state_t *__state = new vdotr_d_single_vdotr_d_single_state_t;

    if (__result) {
        delete __state;
        return nullptr;
    }

    return __state;
}

DACE_EXPORTED int __dace_exit_vdotr_d_single_vdotr_d_single(vdotr_d_single_vdotr_d_single_state_t *__state)
{

    int __err = 0;
    delete __state;
    return __err;
}
