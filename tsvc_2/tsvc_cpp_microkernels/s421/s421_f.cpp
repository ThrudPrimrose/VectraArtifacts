#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ===============================
// %4.1f – %4.2f Storage / aliasing
// ===============================

// s421_f: xx = flat_2d_array; yy = xx;
// xx[i] = yy[i+1] + a[i];
void s421_f(const float *__restrict__ a,
                    float *__restrict__ flat_2d_array, int iterations,
                    int len_1d, std::int64_t * __restrict__ time_ns) {
  auto t1 = clock_highres::now();

  for (int nl = 0; nl < 4 * iterations; ++nl) {
    for (int i = 0; i < len_1d - 1; ++i) {
      flat_2d_array[i] = flat_2d_array[i + 1] + a[i];
    }
  }

  auto t2 = clock_highres::now();
  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
