#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ------------------------------------------------------------
// s314_d_single: max reduction over a
// ------------------------------------------------------------
void s314_d_single(const double *__restrict__ a, int len_1d,
                    std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;

  auto t1 = clock::now();
  {
    double x;
      x = a[0];
      for (int i = 0; i < len_1d; ++i) {
        if (a[i] > x) {
          x = a[i];
        }
      }
  }
  auto t2 = clock::now();

  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
