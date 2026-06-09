#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ------------------------------------------------------------
// s316_f_single: min reduction over a
// ------------------------------------------------------------
void s316_f_single(const float *__restrict__ a, float *__restrict__ result,
                    int iterations, int len_1d,
                    std::int64_t * __restrict__ time_ns) {

  auto t1 = clock_highres::now();
  {
    float x;
    x = a[0];
    for (int i = 1; i < len_1d; ++i) {
      if (a[i] < x) {
        x = a[i];
      }
    }
    result[0] = x;
  }
  auto t2 = clock_highres::now();

  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
