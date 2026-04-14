#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ======================
// %3.5f – Loop rerolling
// ======================

// s351_f: unrolled SAXPY (5-way)
void s351_f(float *__restrict__ a, const float *__restrict__ b,
                    const float *__restrict__ c, int iterations, int len_1d,
                    std::int64_t * __restrict__ time_ns) {
  auto t1 = clock_highres::now();

  float alpha = c[0];
  for (int nl = 0; nl < 8 * iterations; ++nl) {
    for (int i = 0; i < len_1d; i += 4) {
      a[i] += alpha * b[i];
      a[i + 1] += alpha * b[i + 1];
      a[i + 2] += alpha * b[i + 2];
      a[i + 3] += alpha * b[i + 3];
    }
  }

  auto t2 = clock_highres::now();
  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
