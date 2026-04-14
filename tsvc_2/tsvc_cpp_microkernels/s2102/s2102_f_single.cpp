#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ------------------------------------------------------------
// s2102_f_single
// ------------------------------------------------------------
void s2102_f_single(float *__restrict__ aa, int len_2d,
                     std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;

  auto t1 = clock::now();
  {
      for (int i = 0; i < len_2d; i++) {
        for (int j = 0; j < len_2d; j++) {
          aa[j * len_2d + i] = 0.0f;
        }
        aa[i * len_2d + i] = 1.0f;
      }
  }
  auto t2 = clock::now();

  *time_ns =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
