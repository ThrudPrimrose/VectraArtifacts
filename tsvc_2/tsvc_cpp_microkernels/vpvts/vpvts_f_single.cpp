#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ============================================================
// vpvts_f_single — vector plus vector times scalar
// ============================================================

void vpvts_f_single(float *__restrict__ a, const float *__restrict__ b, int len_1d, float s,
                     std::int64_t * __restrict__ time_ns) {
  auto t1 = clock_highres::now();

    for (int i = 0; i < len_1d; ++i) {
      a[i] += b[i] * s;
    }

  auto t2 = clock_highres::now();
  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
