#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// s124_d_single: induction variable under both sides of if (same value)
void s124_d_single(double *__restrict__ a, const double *__restrict__ b,
                    const double *__restrict__ c, const double *__restrict__ d,
                    const double *__restrict__ e,
                    const int len_1d, std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;
  auto t1 = clock::now();
  {
    int j;
      j = -1;
      for (int i = 0; i < len_1d; i++) {
        if (b[i] > 0.0) {
          j++;
          a[j] = b[i] + d[i] * e[i];
        } else {
          j++;
          a[j] = c[i] + d[i] * e[i];
        }
      }
  }
  auto t2 = clock::now();
  std::int64_t ns =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
  time_ns[0] = ns;
}

} // extern "C"
