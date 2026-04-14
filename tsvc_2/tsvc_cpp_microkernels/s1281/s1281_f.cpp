#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ------------------------------------------------------------
// s1281_f
// ------------------------------------------------------------
void s1281_f(float *__restrict__ a, float *__restrict__ b,
                     const float *__restrict__ c, const float *__restrict__ d,
                     const float *__restrict__ e, int iterations, int len_1d,
                     std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;

  auto t1 = clock::now();
  {
    for (int nl = 0; nl < 4 * iterations; nl++) {
      for (int i = 0; i < len_1d; i++) {
        float x = b[i] * c[i] + a[i] * d[i] + e[i];
        a[i] = x - 1.0f;
        b[i] = x;
      }
    }
  }
  auto t2 = clock::now();

  *time_ns =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
