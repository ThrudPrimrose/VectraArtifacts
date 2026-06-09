#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ext_break_find_first_f (s481): if d[i] < 0 break; a[i] = a[i] + b[i]*c[i]
void ext_break_find_first_f(float *__restrict__ a, const float *__restrict__ b,
                                    const float *__restrict__ c, const float *__restrict__ d, const int len_1d,
                                    std::int64_t * __restrict__ time_ns) {
  auto t1 = clock_highres::now();
  for (int i = 0; i < len_1d; ++i) {
    if (d[i] < 0.0f) break;
    a[i] = a[i] + b[i] * c[i];
  }
  auto t2 = clock_highres::now();
  time_ns[0] = std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
