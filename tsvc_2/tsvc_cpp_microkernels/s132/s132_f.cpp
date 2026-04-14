#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ------------------------------------------------------------
// s132_f
// aa[j][i] = aa[k][i-1] + b[i] * c[1]
// j = 0, k = 1
// ------------------------------------------------------------
void s132_f(float *__restrict__ aa, const float *__restrict__ b,
                    const float *__restrict__ c, const int iterations,
                    const int len_2d, std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;
  const int j = 0;
  const int k = 1;

  auto t1 = clock::now();
  {
    for (int nl = 0; nl < 400 * iterations; ++nl) {
      for (int i = 1; i < len_2d; ++i) {
        aa[j * len_2d + i] = aa[k * len_2d + (i - 1)] + b[i] * c[1];
      }
    }
  }
  auto t2 = clock::now();
  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
