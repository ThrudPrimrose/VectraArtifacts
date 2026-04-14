#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ============================================================================
// s252_f
// ============================================================================
void s252_f(float *__restrict__ a, const float *__restrict__ b,
                    const float *__restrict__ c, const int iterations,
                    const int len_1d, std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;

  auto t1 = clock::now();
  {
    for (int nl = 0; nl < iterations; ++nl) {
      float t = 0.0f;
      for (int i = 0; i < len_1d; ++i) {
        float s = b[i] * c[i];
        a[i] = s + t;
        t = s;
      }
    }
  }

  auto t2 = clock::now();
  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
