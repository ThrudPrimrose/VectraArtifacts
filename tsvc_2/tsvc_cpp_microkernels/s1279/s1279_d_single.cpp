#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// s1279_d_single: uses a, b, c, d, e
void s1279_d_single(const double *__restrict__ a, const double *__restrict__ b,
                     double *__restrict__ c, const double *__restrict__ d,
                     const double *__restrict__ e, int len_1d,
                     std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;
  auto t1 = clock::now();

    for (int i = 0; i < len_1d; ++i) {
      if (a[i] < 0.0) {
        if (b[i] > a[i]) {
          c[i] += d[i] * e[i];
        }
      }
    }

  auto t2 = clock::now();
  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
