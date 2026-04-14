#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// s279_f_single: uses a, b, c, d, e
void s279_f_single(float *__restrict__ a, float *__restrict__ b,
                    float *__restrict__ c, const float *__restrict__ d,
                    const float *__restrict__ e, int len_1d,
                    std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;
  auto t1 = clock::now();

    for (int i = 0; i < len_1d; ++i) {
      if (a[i] > 0.0f) {
        c[i] = -c[i] + e[i] * e[i];
      } else {
        b[i] = -b[i] + d[i] * d[i];
        if (b[i] > a[i]) {
          c[i] += d[i] * e[i];
        }
      }
      a[i] = b[i] + c[i] * d[i];
    }

  auto t2 = clock::now();
  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
