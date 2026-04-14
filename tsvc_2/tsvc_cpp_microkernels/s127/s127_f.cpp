#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// s127_f: induction variable with multiple increments
void s127_f(float *__restrict__ a, const float *__restrict__ b,
                    const float *__restrict__ c, const float *__restrict__ d,
                    const float *__restrict__ e, const int iterations,
                    const int len_1d, std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;
  auto t1 = clock::now();
  {
    int j;
    for (int nl = 0; nl < 2 * iterations; nl++) {
      j = -1;
      for (int i = 0; i < len_1d / 2; i++) {
        j++;
        a[j] = b[i] + c[i] * d[i];
        j++;
        a[j] = b[i] + d[i] * e[i];
      }
    }
  }
  auto t2 = clock::now();
  std::int64_t ns =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
  time_ns[0] = ns;
}

} // extern "C"
