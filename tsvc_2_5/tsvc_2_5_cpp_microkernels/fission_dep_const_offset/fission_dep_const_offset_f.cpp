#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// fission_dep_const_offset_f: body A carries a constant-offset-2 dep, body B independent
void fission_dep_const_offset_f(float *__restrict__ a, float *__restrict__ b, const float *__restrict__ x,
                                        const float *__restrict__ y, const float *__restrict__ z, const int len_1d,
                                        std::int64_t * __restrict__ time_ns) {
  auto t1 = clock_highres::now();
  a[0] = x[0];
  a[1] = x[1];
  for (int i = 2; i < len_1d; ++i) {
    a[i] = a[i - 2] + x[i];
    b[i] = y[i] * z[i];
  }
  auto t2 = clock_highres::now();
  time_ns[0] = std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
