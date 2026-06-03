#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// fission_dep_then_indep_f: body A carries a unit-offset dep on `a`, body B independent
void fission_dep_then_indep_f(float *__restrict__ a, float *__restrict__ b, const float *__restrict__ x,
                                      const float *__restrict__ y, const int len_1d, std::int64_t * __restrict__ time_ns) {
  auto t1 = clock_highres::now();
  a[0] = x[0];
  for (int i = 1; i < len_1d; ++i) {
    a[i] = a[i - 1] + x[i];
    b[i] = y[i] * 2.0f;
  }
  auto t2 = clock_highres::now();
  time_ns[0] = std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
