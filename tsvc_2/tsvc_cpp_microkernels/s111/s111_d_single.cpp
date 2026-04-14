#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// s111_d_single: a[i] = a[i-1] + b[i] for odd i
void s111_d_single(double *__restrict__ a, const double *__restrict__ b, const int len_1d,
                    std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;

  auto t1 = clock::now();
  {
      for (int i = 1; i < len_1d; i += 2) {
        a[i] = a[i - 1] + b[i];
      }
  }
  auto t2 = clock::now();

  std::int64_t ns =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
  time_ns[0] = ns;
}

} // extern "C"
