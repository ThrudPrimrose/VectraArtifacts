#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// argmax_value_f (s314): x = a[0]; for i: if a[i] > x: x = a[i]; out[0] = x
void argmax_value_f(const float *__restrict__ a, float *__restrict__ out, const int len_1d,
                            std::int64_t * __restrict__ time_ns) {
  auto t1 = clock_highres::now();
  float x = a[0];
  for (int i = 1; i < len_1d; ++i) {
    if (a[i] > x) {
      x = a[i];
    }
  }
  out[0] = x;
  auto t2 = clock_highres::now();
  time_ns[0] = std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
