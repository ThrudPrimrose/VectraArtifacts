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

    for (i = 0; (i < (LEN_1D - 4)); i = (i + 5)) {
        double a_index;
        double b_index;
        double a_slice_times_b_slice;
        double a_index_0;
        double b_index_0;
        double a_slice_times_b_slice_0;
        double a_slice_b_slice_plus_a_slice_b_slice;
        double a_index_1;
        double b_index_1;
        double a_slice_times_b_slice_1;
        double a_slice_b_slice_a_slice_b_slice_plus_a_slice_b_slice;
        double a_index_2;
        double b_index_2;
        double a_slice_times_b_slice_2;
        double a_slice_b_slice_a_slice_b_slice_a_slice_b_slice_plus_a_slice_b_slice;
        double a_index_3;
        double b_index_3;
        double a_slice_times_b_slice_3;
        double a_slice_b_slice_a_slice_b_slice_a_slice_b_slice_a_slice_b_slice_plus_a_slice_b_slice;
        double dot_plus_a_slice_b_slice_a_slice_b_slice_a_slice_b_slice_a_slice_b_slice_a_slice_b_slice;


        dace::CopyND<double, 1, false, 1>::template ConstDst<1>::Copy(
        a + i, &a_index, 1);

        dace::CopyND<double, 1, false, 1>::template ConstDst<1>::Copy(
        a + (i + 1), &a_index_0, 1);

        dace::CopyND<double, 1, false, 1>::template ConstDst<1>::Copy(
        a + (i + 2), &a_index_1, 1);

        dace::CopyND<double, 1, false, 1>::template ConstDst<1>::Copy(
        a + (i + 3), &a_index_2, 1);

        dace::CopyND<double, 1, false, 1>::template ConstDst<1>::Copy(
        a + (i + 4), &a_index_3, 1);

        dace::CopyND<double, 1, false, 1>::template ConstDst<1>::Copy(
        b + i, &b_index, 1);

        dace::CopyND<double, 1, false, 1>::template ConstDst<1>::Copy(
        b + (i + 1), &b_index_0, 1);

        dace::CopyND<double, 1, false, 1>::template ConstDst<1>::Copy(
        b + (i + 2), &b_index_1, 1);

        dace::CopyND<double, 1, false, 1>::template ConstDst<1>::Copy(
        b + (i + 3), &b_index_2, 1);

        dace::CopyND<double, 1, false, 1>::template ConstDst<1>::Copy(
        b + (i + 4), &b_index_3, 1);

        dot += a_index * b_index + a_index_0 * b_index_0 + a_index_1 * b_index_1 + 
            a_index_2 * b_index_2 + a_index_3 *b_index_3;

    }

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
