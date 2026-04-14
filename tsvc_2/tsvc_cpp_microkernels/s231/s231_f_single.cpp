#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ============================================================================
// s231_f_single  (loop interchange, column recursion)
// ============================================================================
void s231_f_single(float *__restrict__ aa, const float *__restrict__ bb, const int len_2d,
                    std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;
  auto t1 = clock::now();
  {
      for (int i = 0; i < len_2d; ++i) {
        for (int j = 1; j < len_2d; ++j) {
          aa[j * len_2d + i] = aa[(j - 1) * len_2d + i] + bb[j * len_2d + i];
        }
      }
  }
  auto t2 = clock::now();
  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
