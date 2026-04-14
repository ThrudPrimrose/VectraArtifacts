#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// s352_f: unrolled dot product (5-way)
void s352_f(const float *__restrict__ a, const float *__restrict__ b,
                    float *__restrict__ c, int iterations, int len_1d,
                    std::int64_t * __restrict__ time_ns) {
  auto t1 = clock_highres::now();

  float dot = 0.0f;
  for (int nl = 0; nl < 8 * iterations; ++nl) {
    dot = 0.0f;
    for (int i = 0; i < len_1d; i += 4) {
      dot += a[i] * b[i] + a[i + 1] * b[i + 1] + a[i + 2] * b[i + 2] +
             a[i + 3] * b[i + 3] + a[i + 4] * b[i + 4];
    }
  }
  c[0] = dot;

  auto t2 = clock_highres::now();
  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
