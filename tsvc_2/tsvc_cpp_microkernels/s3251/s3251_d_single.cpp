#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ------------------------------------------------------------
// s3251_d_single
// ------------------------------------------------------------
void s3251_d_single(double *__restrict__ a, double *__restrict__ b,
                     const double *__restrict__ c, double *__restrict__ d,
                     const double *__restrict__ e, int iterations, int len_1d,
                     std::int64_t * __restrict__ time_ns) {
  auto t1 = clock_highres::now();

  {
    for (int i = 0; i < len_1d - 1; i++) {
      a[i + 1] = b[i] + c[i];
      b[i] = c[i] * e[i];
      d[i] = a[i] * e[i];
    }
  }

  auto t2 = clock_highres::now();
  *time_ns =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
