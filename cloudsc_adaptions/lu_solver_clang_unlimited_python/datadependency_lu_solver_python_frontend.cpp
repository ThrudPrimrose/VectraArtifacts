/* DaCe AUTO-GENERATED FILE. DO NOT MODIFY */
#include <dace/dace.h>
#include "../../include/hash.h"

struct lu_solver_python_frontend_state_t {

};

void __program_lu_solver_python_frontend_internal(lu_solver_python_frontend_state_t*__state, double * __restrict__ zqlhs, double * __restrict__ zqxn, int KLON, int NCLV)
{
    double zqlhs_index;
    double zqlhs_index_0;
    double zqlhs_slice_div_zqlhs_slice;
    double zqlhs_index_1;
    double zqlhs_index_2;
    double zqlhs_index_3;
    double zqlhs_slice_times_zqlhs_slice;
    double zqlhs_slice_minus_zqlhs_slice_zqlhs_slice;
    double zqxn_index;
    double zqlhs_index_4;
    double zqxn_index_0;
    double zqlhs_slice_times_zqxn_slice;
    double zqxn_slice_minus_zqlhs_slice_zqxn_slice;
    double zqxn_index_1;
    double zqlhs_index_5;
    double zqxn_slice_div_zqlhs_slice;
    double zqxn_index_2;
    double zqlhs_index_6;
    double zqxn_index_3;
    double zqlhs_slice_times_zqxn_slice_0;
    double zqxn_slice_minus_zqlhs_slice_zqxn_slice_0;
    double zqxn_index_4;
    double zqlhs_index_7;
    double zqxn_slice_div_zqlhs_slice_0;
    int64_t jn;
    int64_t jm;
    int64_t jl;
    int64_t ik;




    for (jn = 0; (jn < (NCLV - 1)); jn = (jn + 1)) {



        for (jm = (jn + 1); (jm < NCLV); jm = (jm + 1)) {


#pragma clang loop vectorize(assume_safety) interleave(assume_safety)
            for (jl = 0; (jl < KLON); jl = (jl + 1)) {

                {


                    dace::CopyND<double, 1, false, 1>::template ConstDst<1>::Copy(
                    zqlhs + ((((NCLV * NCLV) * jl) + (NCLV * jm)) + jn), &zqlhs_index, 1);

                }
                {


                    dace::CopyND<double, 1, false, 1>::template ConstDst<1>::Copy(
                    zqlhs + ((((NCLV * NCLV) * jl) + (NCLV * jn)) + jn), &zqlhs_index_0, 1);

                }
                {

                    {
                        double __in1 = zqlhs_index;
                        double __in2 = zqlhs_index_0;
                        double __out;

                        ///////////////////
                        // Tasklet code (_Div_)
                        __out = (__in1 / __in2);
                        ///////////////////

                        zqlhs_slice_div_zqlhs_slice = __out;
                    }

                }
                {

                    {
                        double __inp = zqlhs_slice_div_zqlhs_slice;
                        double __out;

                        ///////////////////
                        // Tasklet code (assign_14_16)
                        __out = __inp;
                        ///////////////////

                        zqlhs[((((NCLV * NCLV) * jl) + (NCLV * jm)) + jn)] = __out;
                    }

                }

            }



            for (ik = (jn + 1); (ik < NCLV); ik = (ik + 1)) {


#pragma clang loop vectorize(assume_safety) interleave(assume_safety)
                for (jl = 0; (jl < KLON); jl = (jl + 1)) {

                    {


                        dace::CopyND<double, 1, false, 1>::template ConstDst<1>::Copy(
                        zqlhs + ((((NCLV * NCLV) * jl) + (NCLV * jm)) + ik), &zqlhs_index_1, 1);

                    }
                    {


                        dace::CopyND<double, 1, false, 1>::template ConstDst<1>::Copy(
                        zqlhs + ((((NCLV * NCLV) * jl) + (NCLV * jm)) + jn), &zqlhs_index_2, 1);

                    }
                    {


                        dace::CopyND<double, 1, false, 1>::template ConstDst<1>::Copy(
                        zqlhs + ((((NCLV * NCLV) * jl) + (NCLV * jn)) + ik), &zqlhs_index_3, 1);

                    }
                    {

                        {
                            double __in1 = zqlhs_index_2;
                            double __in2 = zqlhs_index_3;
                            double __out;

                            ///////////////////
                            // Tasklet code (_Mult_)
                            __out = (__in1 * __in2);
                            ///////////////////

                            zqlhs_slice_times_zqlhs_slice = __out;
                        }

                    }
                    {

                        {
                            double __in1 = zqlhs_index_1;
                            double __in2 = zqlhs_slice_times_zqlhs_slice;
                            double __out;

                            ///////////////////
                            // Tasklet code (_Sub_)
                            __out = (__in1 - __in2);
                            ///////////////////

                            zqlhs_slice_minus_zqlhs_slice_zqlhs_slice = __out;
                        }

                    }
                    {

                        {
                            double __inp = zqlhs_slice_minus_zqlhs_slice_zqlhs_slice;
                            double __out;

                            ///////////////////
                            // Tasklet code (assign_17_20)
                            __out = __inp;
                            ///////////////////

                            zqlhs[((((NCLV * NCLV) * jl) + (NCLV * jm)) + ik)] = __out;
                        }

                    }

                }


            }


        }


    }


    for (jn = 1; (jn < NCLV); jn = (jn + 1)) {


        for (jm = 0; (jm < jn); jm = (jm + 1)) {


#pragma clang loop vectorize(assume_safety) interleave(assume_safety)
            for (jl = 0; (jl < KLON); jl = (jl + 1)) {

                {


                    dace::CopyND<double, 1, false, 1>::template ConstDst<1>::Copy(
                    zqxn + ((NCLV * jl) + jn), &zqxn_index, 1);

                }
                {


                    dace::CopyND<double, 1, false, 1>::template ConstDst<1>::Copy(
                    zqlhs + ((((NCLV * NCLV) * jl) + (NCLV * jn)) + jm), &zqlhs_index_4, 1);

                }
                {


                    dace::CopyND<double, 1, false, 1>::template ConstDst<1>::Copy(
                    zqxn + ((NCLV * jl) + jm), &zqxn_index_0, 1);

                }
                {

                    {
                        double __in1 = zqlhs_index_4;
                        double __in2 = zqxn_index_0;
                        double __out;

                        ///////////////////
                        // Tasklet code (_Mult_)
                        __out = (__in1 * __in2);
                        ///////////////////

                        zqlhs_slice_times_zqxn_slice = __out;
                    }

                }
                {

                    {
                        double __in1 = zqxn_index;
                        double __in2 = zqlhs_slice_times_zqxn_slice;
                        double __out;

                        ///////////////////
                        // Tasklet code (_Sub_)
                        __out = (__in1 - __in2);
                        ///////////////////

                        zqxn_slice_minus_zqlhs_slice_zqxn_slice = __out;
                    }

                }
                {

                    {
                        double __inp = zqxn_slice_minus_zqlhs_slice_zqxn_slice;
                        double __out;

                        ///////////////////
                        // Tasklet code (assign_22_16)
                        __out = __inp;
                        ///////////////////

                        zqxn[((NCLV * jl) + jn)] = __out;
                    }

                }

            }


        }


    }


#pragma clang loop vectorize(assume_safety) interleave(assume_safety)
    for (jl = 0; (jl < KLON); jl = (jl + 1)) {


        {


            dace::CopyND<double, 1, false, 1>::template ConstDst<1>::Copy(
            zqxn + (((NCLV * jl) + NCLV) - 1), &zqxn_index_1, 1);

        }


        {


            dace::CopyND<double, 1, false, 1>::template ConstDst<1>::Copy(
            zqlhs + (((((NCLV * NCLV) * jl) + (NCLV * (NCLV - 1))) + NCLV) - 1), &zqlhs_index_5, 1);

        }
        {

            {
                double __in1 = zqxn_index_1;
                double __in2 = zqlhs_index_5;
                double __out;

                ///////////////////
                // Tasklet code (_Div_)
                __out = (__in1 / __in2);
                ///////////////////

                zqxn_slice_div_zqlhs_slice = __out;
            }

        }

        {

            {
                double __inp = zqxn_slice_div_zqlhs_slice;
                double __out;

                ///////////////////
                // Tasklet code (assign_25_8)
                __out = __inp;
                ///////////////////

                zqxn[(((NCLV * jl) + NCLV) - 1)] = __out;
            }

        }

    }





    for (jn = (NCLV - 2); (jn > -1); jn = (jn + -1)) {



        for (jm = (jn + 1); (jm < NCLV); jm = (jm + 1)) {


#pragma clang loop vectorize(assume_safety) interleave(assume_safety)
            for (jl = 0; (jl < KLON); jl = (jl + 1)) {

                {


                    dace::CopyND<double, 1, false, 1>::template ConstDst<1>::Copy(
                    zqxn + ((NCLV * jl) + jn), &zqxn_index_2, 1);

                }
                {


                    dace::CopyND<double, 1, false, 1>::template ConstDst<1>::Copy(
                    zqlhs + ((((NCLV * NCLV) * jl) + (NCLV * jn)) + jm), &zqlhs_index_6, 1);

                }
                {


                    dace::CopyND<double, 1, false, 1>::template ConstDst<1>::Copy(
                    zqxn + ((NCLV * jl) + jm), &zqxn_index_3, 1);

                }
                {

                    {
                        double __in1 = zqlhs_index_6;
                        double __in2 = zqxn_index_3;
                        double __out;

                        ///////////////////
                        // Tasklet code (_Mult_)
                        __out = (__in1 * __in2);
                        ///////////////////

                        zqlhs_slice_times_zqxn_slice_0 = __out;
                    }

                }
                {

                    {
                        double __in1 = zqxn_index_2;
                        double __in2 = zqlhs_slice_times_zqxn_slice_0;
                        double __out;

                        ///////////////////
                        // Tasklet code (_Sub_)
                        __out = (__in1 - __in2);
                        ///////////////////

                        zqxn_slice_minus_zqlhs_slice_zqxn_slice_0 = __out;
                    }

                }
                {

                    {
                        double __inp = zqxn_slice_minus_zqlhs_slice_zqxn_slice_0;
                        double __out;

                        ///////////////////
                        // Tasklet code (assign_30_16)
                        __out = __inp;
                        ///////////////////

                        zqxn[((NCLV * jl) + jn)] = __out;
                    }

                }

            }


        }


#pragma clang loop vectorize(assume_safety) interleave(assume_safety)
        for (jl = 0; (jl < KLON); jl = (jl + 1)) {

            {


                dace::CopyND<double, 1, false, 1>::template ConstDst<1>::Copy(
                zqxn + ((NCLV * jl) + jn), &zqxn_index_4, 1);

            }
            {


                dace::CopyND<double, 1, false, 1>::template ConstDst<1>::Copy(
                zqlhs + ((((NCLV * NCLV) * jl) + (NCLV * jn)) + jn), &zqlhs_index_7, 1);

            }
            {

                {
                    double __in1 = zqxn_index_4;
                    double __in2 = zqlhs_index_7;
                    double __out;

                    ///////////////////
                    // Tasklet code (_Div_)
                    __out = (__in1 / __in2);
                    ///////////////////

                    zqxn_slice_div_zqlhs_slice_0 = __out;
                }

            }
            {

                {
                    double __inp = zqxn_slice_div_zqlhs_slice_0;
                    double __out;

                    ///////////////////
                    // Tasklet code (assign_32_12)
                    __out = __inp;
                    ///////////////////

                    zqxn[((NCLV * jl) + jn)] = __out;
                }

            }

        }


    }

}

DACE_EXPORTED void __program_lu_solver_python_frontend(lu_solver_python_frontend_state_t *__state, double * __restrict__ zqlhs, double * __restrict__ zqxn, int KLON, int NCLV)
{
    __program_lu_solver_python_frontend_internal(__state, zqlhs, zqxn, KLON, NCLV);
}

DACE_EXPORTED lu_solver_python_frontend_state_t *__dace_init_lu_solver_python_frontend(int KLON, int NCLV)
{

    int __result = 0;
    lu_solver_python_frontend_state_t *__state = new lu_solver_python_frontend_state_t;

    if (__result) {
        delete __state;
        return nullptr;
    }

    return __state;
}

DACE_EXPORTED int __dace_exit_lu_solver_python_frontend(lu_solver_python_frontend_state_t *__state)
{

    int __err = 0;
    delete __state;
    return __err;
}
