#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ------------------------------------------------------------
// s1161_f
// ------------------------------------------------------------
void s1161_f(float *__restrict__ a, float *__restrict__ b,
                     float *__restrict__ c, const float *__restrict__ d,
                     const float *__restrict__ e, const int iterations,
                     const int len_1d, std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;

  auto t1 = clock::now();
  {
    for (int nl = 0; nl < iterations; ++nl) {
      for (int i = 0; i < len_1d; ++i) {
        if (c[i] < 0.0f) {
          b[i] = a[i] + d[i] * d[i];
        } else {
          a[i] = c[i] + d[i] * e[i];
        }
      }
    }
  }
  auto t2 = clock::now();
  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
