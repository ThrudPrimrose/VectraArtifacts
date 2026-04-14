#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// s113_f: a(i)=a(1) but no actual dependence cycle
void s113_f(float *__restrict__ a, const float *__restrict__ b,
                    const int iterations, const int len_1d,
                    std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;
  auto t1 = clock::now();
  {
    for (int nl = 0; nl < 4 * iterations; nl++) {
      for (int i = 1; i < len_1d; i++) {
        a[i] = a[0] + b[i];
      }
    }
  }
  auto t2 = clock::now();
  std::int64_t ns =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
  time_ns[0] = ns;
}

} // extern "C"
