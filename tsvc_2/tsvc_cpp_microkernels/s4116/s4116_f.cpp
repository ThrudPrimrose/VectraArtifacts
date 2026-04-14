#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// -----------------------------------------------------------------------------
// %4.11f  s4116_f
// -----------------------------------------------------------------------------
void s4116_f(const float *__restrict__ a,
                     const float *__restrict__ aa, const int * __restrict__ ip,
                     float *__restrict__ sum_out, int inc, int iterations,
                     int j, int len_1d, int len_2d, std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;
  auto t1 = clock::now();

  for (int nl = 0; nl < 100 * iterations; ++nl) {
    sum_out[0] = 0.0f;
    for (int i = 0; i < len_2d - 1; ++i) {
      int off = inc + i;
      sum_out[0] += a[off] * aa[(j - 1) * len_2d + ip[i]];
    }
  }

  auto t2 = clock::now();
  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
