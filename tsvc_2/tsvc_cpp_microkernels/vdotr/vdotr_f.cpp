#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ============================================================
// vdotr_f — vector dot product
// ============================================================

void vdotr_f(const float *__restrict__ a, const float *__restrict__ b,
                     float *__restrict__ dot_out, int iterations, int len_1d,
                     std::int64_t * __restrict__ time_ns) {
  auto t1 = clock_highres::now();

  float dot = 0.0f;
  for (int nl = 0; nl < iterations * 10; ++nl) {
    dot = 0.0f;
    for (int i = 0; i < len_1d; ++i) {
      dot += a[i] * b[i];
    }
  }

  auto t2 = clock_highres::now();
  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
  *dot_out = dot;
}

} // extern "C"
