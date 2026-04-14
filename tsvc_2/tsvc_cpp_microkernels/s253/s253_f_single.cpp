#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ============================================================================
// s253_f_single
// ============================================================================
void s253_f_single(float *__restrict__ a, float *__restrict__ b,
                    float *__restrict__ c, const float *__restrict__ d, const int len_1d,
                    std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;

  auto t1 = clock::now();
  {
      float s = 0.0f;
      for (int i = 0; i < len_1d; ++i) {
        if (a[i] > b[i]) {
          s = a[i] - b[i] * d[i];
          c[i] += s;
          a[i] = s;
        }
      }
  }

  auto t2 = clock::now();
  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
