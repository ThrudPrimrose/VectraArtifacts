#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ============================================================================
// s1221_f  (runtime symbolic resolution)
// ============================================================================
void s1221_f(float *__restrict__ a, float *__restrict__ b,
                     const int iterations, const int len_1d,
                     std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;

  auto t1 = clock::now();
  {
    for (int nl = 0; nl < iterations; ++nl) {
      for (int i = 4; i < len_1d; ++i) {
        b[i] = b[i - 4] + a[i];
      }
    }
  }

  auto t2 = clock::now();
  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
