#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// s114_f_single: transpose vectorization - Jump in data access
void s114_f_single(float *__restrict__ aa, const float *__restrict__ bb, const int len_2d, const int vlen,
                    std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;
  auto t1 = clock::now();
  {
      for (int i = 0; i < len_2d / vlen; i++) {
        for (int j = 0; j < i * vlen; j++) {
          aa[i * len_2d + j] = aa[j * len_2d + i] + bb[i * len_2d + j];
        }
      }
  }
  auto t2 = clock::now();
  std::int64_t ns =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
  time_ns[0] = ns;
}

} // extern "C"
