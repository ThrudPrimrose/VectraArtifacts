#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ------------------------------------------------------------
// s162_f
// ------------------------------------------------------------
void s162_f(float *__restrict__ a, const float *__restrict__ b,
                    const float *__restrict__ c, const int iterations,
                    const int k, const int len_1d, std::int64_t * __restrict__ time_ns) {

  auto t1 = clock_highres::now();
  {
    for (int nl = 0; nl < iterations; ++nl) {
      if (k > 0) {
        for (int i = 0; i < len_1d - k; ++i) {
          a[i] = a[i + k] + b[i] * c[i];
        }
      }
    }
  }
  auto t2 = clock_highres::now();
  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
