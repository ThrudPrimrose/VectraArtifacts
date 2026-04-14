#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ------------------------------------------------------------
// s173_f
// ------------------------------------------------------------
void s173_f(float *__restrict__ a, const float *__restrict__ b,
                    const int iterations, const int len_1d,
                    std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;
  int k = len_1d / 2;

  auto t1 = clock::now();
  {
    for (int nl = 0; nl < 10 * iterations; ++nl) {
      for (int i = 0; i < len_1d / 2; ++i) {
        a[i + k] = a[i] + b[i];
      }
    }
  }

  auto t2 = clock::now();
  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
