#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// -----------------------------------------------------------------------------
// %4.11f  s4112_f
// -----------------------------------------------------------------------------
void s4112_f(float *__restrict__ a, const float *__restrict__ b,
                     const int * __restrict__ ip, int iterations, int len_1d,
                     std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;
  auto t1 = clock::now();

  for (int nl = 0; nl < iterations; ++nl) {
    for (int i = 0; i < len_1d; ++i) {
      a[i] += b[ip[i]] * 2.0f;
    }
  }

  auto t2 = clock::now();
  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
