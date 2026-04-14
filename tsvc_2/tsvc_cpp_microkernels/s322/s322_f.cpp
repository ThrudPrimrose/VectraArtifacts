#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// s322_f: second-order linear recurrence
void s322_f(float *__restrict__ a, const float *__restrict__ b,
                    const float *__restrict__ c, int iterations, int len_1d,
                    std::int64_t * __restrict__ time_ns) {
  auto t1 = clock_highres::now();

  for (int nl = 0; nl < iterations / 2; ++nl) {
    for (int i = 2; i < len_1d; ++i) {
      a[i] = a[i] + a[i - 1] * b[i] + a[i - 2] * c[i];
    }
  }

  auto t2 = clock_highres::now();
  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
