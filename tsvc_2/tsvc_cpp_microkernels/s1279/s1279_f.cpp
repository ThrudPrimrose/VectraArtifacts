#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// s1279_f: uses a, b, c, d, e
void s1279_f(const float *__restrict__ a, const float *__restrict__ b,
                     float *__restrict__ c, const float *__restrict__ d,
                     const float *__restrict__ e, int iterations, int len_1d,
                     std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;
  auto t1 = clock::now();

  for (int nl = 0; nl < iterations; ++nl) {
    for (int i = 0; i < len_1d; ++i) {
      if (a[i] < 0.0f) {
        if (b[i] > a[i]) {
          c[i] += d[i] * e[i];
        }
      }
    }
  }

  auto t2 = clock::now();
  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
