#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// s323_f_single: coupled recurrence
void s323_f_single(float *__restrict__ a, float *__restrict__ b,
                    const float *__restrict__ c, const float *__restrict__ d,
                    const float *__restrict__ e, int len_1d,
                    std::int64_t * __restrict__ time_ns) {
  auto t1 = clock_highres::now();

    for (int i = 1; i < len_1d; ++i) {
      a[i] = b[i - 1] + c[i] * d[i];
      b[i] = a[i] + c[i] * e[i];
    }

  auto t2 = clock_highres::now();
  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
