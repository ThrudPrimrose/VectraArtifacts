#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ------------------------------------------------------------
// s256_f_single
// ------------------------------------------------------------
void s256_f_single(float *__restrict__ a, float *__restrict__ aa,
                    const float *__restrict__ bb, const float *__restrict__ d, int len_2d, std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;
  auto t1 = clock::now();

  {
      for (int i = 0; i < len_2d; i++) {
        for (int j = 1; j < len_2d; j++) {
          a[j] = 1.0f - a[j - 1];
          aa[j * len_2d + i] = a[j] + bb[j * len_2d + i] * d[j];
        }
      }
  }

  auto t2 = clock::now();
  *time_ns =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
