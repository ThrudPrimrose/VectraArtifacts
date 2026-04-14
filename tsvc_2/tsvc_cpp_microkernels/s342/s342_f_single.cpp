#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// s342_f_single: unpacking using a as mask into b
void s342_f_single(float *__restrict__ a, const float *__restrict__ b, int len_1d, std::int64_t * __restrict__ time_ns) {
  auto t1 = clock_highres::now();

  int j = 0;
    j = -1;
    for (int i = 0; i < len_1d; ++i) {
      if (a[i] > 0.0f) {
        ++j;
        a[i] = b[j];
      }
    }

  auto t2 = clock_highres::now();
  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
