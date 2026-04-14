#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ------------------------------------------------------------
// s2251_d
// ------------------------------------------------------------
void s2251_d(double *__restrict__ a, double *__restrict__ b,
                     const double *__restrict__ c, const double *__restrict__ d,
                     const double *__restrict__ e, int iterations, int len_1d,
                     std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;
  auto t1 = clock::now();

  {
    for (int nl = 0; nl < iterations; nl++) {
      double s = 0.0;
      for (int i = 0; i < len_1d; i++) {
        a[i] = s * e[i];
        s = b[i] + c[i];
        b[i] = a[i] + d[i];
      }
    }
  }

  auto t2 = clock::now();
  *time_ns =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
