#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ------------------------------------------------------------
// s281_f_single
// ------------------------------------------------------------
void s281_f_single(float *__restrict__ a, float *__restrict__ b,
                    const float *__restrict__ c, int len_1d,
                    std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;

  auto t1 = clock::now();
  {
      for (int i = 0; i < len_1d; i++) {
        float x = a[len_1d - i - 1] + b[i] * c[i];
        a[i] = x - 1.0f;
        b[i] = x;
      }
  }
  auto t2 = clock::now();

  *time_ns =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
