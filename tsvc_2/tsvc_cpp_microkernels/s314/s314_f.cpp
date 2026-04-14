#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ------------------------------------------------------------
// s314_f: max reduction over a
// ------------------------------------------------------------
void s314_f(const float *__restrict__ a, float *__restrict__ result,
                    int iterations, int len_1d,
                    std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;

  auto t1 = clock::now();
  {
    float x;
    for (int nl = 0; nl < iterations; ++nl) {
      x = a[0];
      for (int i = 0; i < len_1d; ++i) {
        if (a[i] > x) {
          x = a[i];
        }
      }
    }
    result[0] = x;
  }
  auto t2 = clock::now();

  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
