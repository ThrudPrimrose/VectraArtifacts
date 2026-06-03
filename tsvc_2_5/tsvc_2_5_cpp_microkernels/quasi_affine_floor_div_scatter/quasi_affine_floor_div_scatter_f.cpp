#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// quasi_affine_floor_div_scatter_f: b[i / 2] += a[i] (pair-stripe reduction)
void quasi_affine_floor_div_scatter_f(const float *__restrict__ a, float *__restrict__ b, const int len_1d,
                                              std::int64_t * __restrict__ time_ns) {
  auto t1 = clock_highres::now();
  for (int i = 0; i < 2 * len_1d; ++i) {
    b[i / 2] += a[i];
  }
  auto t2 = clock_highres::now();
  time_ns[0] = std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
