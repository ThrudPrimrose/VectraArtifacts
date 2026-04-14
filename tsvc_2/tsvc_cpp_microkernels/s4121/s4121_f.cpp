#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

static inline float tsvc_mul_f(float a, float b) { return a * b; }


// -----------------------------------------------------------------------------
// %4.12f  s4121_f
// -----------------------------------------------------------------------------
void s4121_f(float *__restrict__ a, const float *__restrict__ b,
                     const float *__restrict__ c, int iterations, int len_1d,
                     std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;
  auto t1 = clock::now();

  for (int nl = 0; nl < iterations; ++nl) {
    for (int i = 0; i < len_1d; ++i) {
      a[i] += tsvc_mul_f(b[i], c[i]);
    }
  }

  auto t2 = clock::now();
  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
