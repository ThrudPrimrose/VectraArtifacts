#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ------------------------------------------------------------
// s261_f
// ------------------------------------------------------------
void s261_f(float *__restrict__ a, float *__restrict__ b,
                    float *__restrict__ c, const float *__restrict__ d,
                    int iterations, int len_1d, std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;
  auto t1 = clock::now();

  {
    for (int nl = 0; nl < iterations; nl++) {
      for (int i = 1; i < len_1d; i++) {
        float t = a[i] + b[i];
        a[i] = t + c[i - 1];
        c[i] = c[i] * d[i];
      }
    }
  }

  auto t2 = clock::now();
  *time_ns =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
