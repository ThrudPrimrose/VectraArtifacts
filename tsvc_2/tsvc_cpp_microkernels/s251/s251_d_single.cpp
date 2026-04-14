#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ------------------------------------------------------------
// s251_d_single
// ------------------------------------------------------------
void s251_d_single(double *__restrict__ a, const double *__restrict__ b,
                    const double *__restrict__ c, const double *__restrict__ d, int len_1d, std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;
  auto t1 = clock::now();

  {
      for (int i = 0; i < len_1d; i++) {
        double s = b[i] + c[i] * d[i];
        a[i] = s * s;
      }
  }

  auto t2 = clock::now();
  *time_ns =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
