#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ------------------------------------------------------------
// s293_f
// ------------------------------------------------------------
void s293_f(float *__restrict__ a, int iterations, int len_1d,
                    std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;

  auto t1 = clock::now();
  {
    float a0 = a[0];
    for (int nl = 0; nl < 4 * iterations; nl++) {
      for (int i = 0; i < len_1d; i++) {
        a[i] = a0;
      }
    }
  }
  auto t2 = clock::now();

  *time_ns =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
