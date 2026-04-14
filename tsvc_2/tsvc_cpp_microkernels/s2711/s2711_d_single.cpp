#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// s2711_d_single: uses a, b, c
void s2711_d_single(double *__restrict__ a, const double *__restrict__ b,
                     const double *__restrict__ c, int len_1d,
                     std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;
  auto t1 = clock::now();

    for (int i = 0; i < len_1d; ++i) {
      if (b[i] != 0.0) {
        a[i] += b[i] * c[i];
      }
    }

  auto t2 = clock::now();
  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
