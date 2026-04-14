#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ------------------------------------------------------------
// s319_f: coupled reductions on a and b
// ------------------------------------------------------------
void s319_f(float *__restrict__ a, float *__restrict__ b,
                    const float *__restrict__ c, const float *__restrict__ d,
                    const float *__restrict__ e, int iterations, int len_1d,
                    std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;

  auto t1 = clock::now();
  {
    float sum;
    for (int nl = 0; nl < 2 * iterations; ++nl) {
      sum = 0.0f;
      for (int i = 0; i < len_1d; ++i) {
        a[i] = c[i] + d[i];
        sum += a[i];
        b[i] = c[i] + e[i];
        sum += b[i];
      }
      b[0] = sum;
    }
  }
  auto t2 = clock::now();

  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
