#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ------------------------------------------------------------
// s272_f_single
// ------------------------------------------------------------
void s272_f_single(float *__restrict__ a, float *__restrict__ b,
                    const float *__restrict__ c, const float *__restrict__ d,
                    const float *__restrict__ e, int len_1d,
                    int threshold, std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;
  auto t1 = clock::now();

  {
      for (int i = 0; i < len_1d; i++) {
        if (e[i] >= threshold) {
          a[i] += c[i] * d[i];
          b[i] += c[i] * c[i];
        }
      }
  }

  auto t2 = clock::now();
  *time_ns =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
