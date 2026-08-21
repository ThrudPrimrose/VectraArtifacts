import dace
import copy
from dace.transformation.auto import auto_optimize as aopt

N = dace.symbol('N', dtype=dace.int64)

@dace.program
def reduction(A: dace.float64[1], B: dace.float64[N]):
    for i in dace.map[0:N]:
        A[0] += B[i] * 2.0


sdfg = reduction.to_sdfg()
sdfg.save("reduction.sdfgz")

sdfg.compile()

opt_sdfg = copy.deepcopy(sdfg)
opt_sdfg = aopt.auto_optimize(opt_sdfg, dace.DeviceType.CPU)
opt_sdfg.name += "aopt"
opt_sdfg.save("reduction_opt.sdfgz")

opt_sdfg.compile()


seq_sdfg = copy.deepcopy(sdfg)

for state in seq_sdfg.all_states():
    for node in state.nodes():
        if isinstance(node, dace.nodes.MapEntry):
            node.map.schedule = dace.ScheduleType.Sequential

seq_sdfg.name += "seq"
seq_sdfg.save("reduction_seq.sdfgz")
seq_sdfg.compile()


"""
void __program_reduction_internal(reduction_state_t*__state, double * __restrict__ A, double * __restrict__ B, int64_t N)
{

    {

        {
            #pragma omp parallel for
            for (auto i = 0; i < N; i += 1) {
                double B_slice_times_2_0;
                {
                    double __in1 = B[i];
                    double __out;

                    ///////////////////
                    // Tasklet code (_Mult_)
                    __out = (__in1 * 2.0);
                    ///////////////////

                    B_slice_times_2_0 = __out;
                }
                {
                    double __inp = B_slice_times_2_0;
                    double __out;

                    ///////////////////
                    // Tasklet code (assign_10_8)
                    __out = __inp;
                    ///////////////////

                    dace::wcr_fixed<dace::ReductionType::Sum, double>::reduce_atomic(A, __out);
                }
            }
        }

    }
}
"""

# Would be much faster if we would have:
"""
void __program_reduction_internal(reduction_state_t*__state, double * __restrict__ A, double * __restrict__ B, int64_t N)
{

    {

        {
            double __reduce_acc = 0.0;
            #pragma omp parallel for reduction(+:__reduce_acc)
            for (auto i = 0; i < N; i += 1) {
                double B_slice_times_2_0;
                {
                    double __in1 = B[i];
                    double __out;

                    ///////////////////
                    // Tasklet code (_Mult_)
                    __out = (__in1 * 2.0);
                    ///////////////////

                    B_slice_times_2_0 = __out;
                }
                {
                    double __inp = B_slice_times_2_0;
                    double __out;

                    ///////////////////
                    // Tasklet code (assign_10_8)
                    __out = __inp;
                    ///////////////////

                    // dace::wcr_fixed<dace::ReductionType::Sum, double>::reduce_atomic(A, __out);
                    __reduce_acc += __out;
                }
            }
            A[0] = __reduce_acc;
        }

    }
}
"""