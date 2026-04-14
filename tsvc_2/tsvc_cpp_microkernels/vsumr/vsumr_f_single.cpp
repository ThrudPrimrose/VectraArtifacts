#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ============================================================
// vsumr_f_single — sum reduction
// ============================================================

void vsumr_f_single(const float *__restrict__ a, float *__restrict__ sum_out, int len_1d, std::int64_t * __restrict__ time_ns) {
  auto t1 = clock_highres::now();

  float sum = 0.0f;
    sum = 0.0f;
    for (int i = 0; i < len_1d; ++i) {
      sum += a[i];
    }

  auto t2 = clock_highres::now();
  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
  *sum_out = sum;
}

} // extern "C"
