#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// reroll_saxpy4_f (s351): 4x hand-unrolled saxpy over a step-4 loop
void reroll_saxpy4_f(float *__restrict__ a, const float *__restrict__ b, const int len_1d,
                             std::int64_t * __restrict__ time_ns) {
  auto t1 = clock_highres::now();
  for (int i = 0; i < len_1d; i += 4) {
    a[i] = a[i] + b[i] * 2.0f;
    a[i + 1] = a[i + 1] + b[i + 1] * 2.0f;
    a[i + 2] = a[i + 2] + b[i + 2] * 2.0f;
    a[i + 3] = a[i + 3] + b[i + 3] * 2.0f;
  }
  auto t2 = clock_highres::now();
  time_ns[0] = std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
