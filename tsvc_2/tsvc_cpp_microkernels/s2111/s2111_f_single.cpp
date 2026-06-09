#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ------------------------------------------------------------
// s2111_f_single
// ------------------------------------------------------------
void s2111_f_single(float *__restrict__ aa, int iterations, int len_2d,
                     std::int64_t * __restrict__ time_ns) {

  auto t1 = clock_highres::now();
  {
    for (int j = 1; j < len_2d; j++) {
      for (int i = 1; i < len_2d; i++) {
        float left = aa[j * len_2d + (i - 1)];
        float upper = aa[(j - 1) * len_2d + i];
        aa[j * len_2d + i] = (left + upper) / 1.9f;
      }
    }
  }
  auto t2 = clock_highres::now();

  *time_ns =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
