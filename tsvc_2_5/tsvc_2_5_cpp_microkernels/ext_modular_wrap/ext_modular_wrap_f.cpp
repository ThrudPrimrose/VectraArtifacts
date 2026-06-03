#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ext_modular_wrap_f: a[(i + k) % len_1d] = b[i]
void ext_modular_wrap_f(float *__restrict__ a, const float *__restrict__ b, const int len_1d, const int k,
                                std::int64_t * __restrict__ time_ns) {
  auto t1 = clock_highres::now();
  for (int i = 0; i < len_1d; ++i) {
    a[(i + k) % len_1d] = b[i];
  }
  auto t2 = clock_highres::now();
  time_ns[0] = std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
