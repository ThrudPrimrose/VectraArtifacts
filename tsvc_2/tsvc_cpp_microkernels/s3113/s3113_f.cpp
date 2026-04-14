#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// s3113_f: maximum of absolute value
void s3113_f(const float *__restrict__ a, float *__restrict__ b,
                     int iterations, int len_1d, std::int64_t * __restrict__ time_ns) {
  auto t1 = clock_highres::now();

  float maxv = 0.0f;
  for (int nl = 0; nl < iterations * 4; ++nl) {
    maxv = std::fabs(a[0]);
    for (int i = 0; i < len_1d; ++i) {
      float av = std::fabs(a[i]);
      if (av > maxv) {
        maxv = av;
      }
    }
  }
  b[0] = maxv;

  auto t2 = clock_highres::now();
  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
