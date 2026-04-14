#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// -----------------------------------------------------------------------------
// %4.9  s491_d
// -----------------------------------------------------------------------------
void s491_d(double *__restrict__ a, const double *__restrict__ b,
                    const double *__restrict__ c, const double *__restrict__ d,
                    const int * __restrict__ ip, int iterations, int len_1d,
                    std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;
  auto t1 = clock::now();

  for (int nl = 0; nl < iterations; ++nl) {
    for (int i = 0; i < len_1d; ++i) {
      a[ip[i]] = b[i] + c[i] * d[i];
    }
  }

  auto t2 = clock::now();
  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
