#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// s2275_f: uses a, b, c, d, aa, bb, cc
void s2275_f(float *__restrict__ a, float *__restrict__ aa,
                     const float *__restrict__ b,
                     const float *__restrict__ bb,
                     const float *__restrict__ c,
                     const float *__restrict__ cc,
                     const float *__restrict__ d, int iterations, int len_2d,
                     std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;
  auto t1 = clock::now();

  for (int nl = 0; nl < 100 * (iterations / len_2d); ++nl) {
    for (int i = 0; i < len_2d; ++i) {
      for (int j = 0; j < len_2d; ++j) {
        int idx = j * len_2d + i;
        aa[idx] = aa[idx] + bb[idx] * cc[idx];
      }
      a[i] = b[i] + c[i] * d[i];
    }
  }

  auto t2 = clock::now();
  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
