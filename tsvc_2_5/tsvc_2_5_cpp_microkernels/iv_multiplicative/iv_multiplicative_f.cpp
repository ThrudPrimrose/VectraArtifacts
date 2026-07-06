#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// iv_multiplicative_f: s = 1; for i in [0, len_1d): s *= 0.99f; out[0] = s
void iv_multiplicative_f(float *__restrict__ out, const int len_1d, std::int64_t * __restrict__ time_ns) {
  auto t1 = clock_highres::now();
  float s = 1.0f;
  for (int i = 0; i < len_1d; ++i) {
    s = s * 0.99f;
  }
  out[0] = s;
  auto t2 = clock_highres::now();
  time_ns[0] = std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
