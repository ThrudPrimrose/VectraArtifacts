#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// s1113_f_single: one iteration dependency on a(LEN_1D/2) but still vectorizable
void s1113_f_single(float *__restrict__ a, const float *__restrict__ b, const int len_1d,
                     std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;
  auto t1 = clock::now();
  {
      for (int i = 0; i < len_1d; i++) {
        a[i] = a[len_1d / 2] + b[i];
      }
  }
  auto t2 = clock::now();
  std::int64_t ns =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
  time_ns[0] = ns;
}

} // extern "C"
