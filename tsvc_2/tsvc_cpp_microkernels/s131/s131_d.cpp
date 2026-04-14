#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// s131_d: forward substitution
void s131_d(double *__restrict__ a, const double *__restrict__ b,
                    const int iterations, const int len_1d,
                    std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;
  auto t1 = clock::now();
  {
    int m = 1;
    for (int nl = 0; nl < 5 * iterations; nl++) {
      for (int i = 0; i < len_1d - 1; i++) {
        a[i] = a[i + m] + b[i];
      }
    }
  }
  auto t2 = clock::now();
  std::int64_t ns =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
  time_ns[0] = ns;
}

} // extern "C"
