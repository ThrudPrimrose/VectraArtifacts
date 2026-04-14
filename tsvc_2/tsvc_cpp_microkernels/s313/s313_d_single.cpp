#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ------------------------------------------------------------
// s313_d_single: dot product a·b
// ------------------------------------------------------------
void s313_d_single(const double *__restrict__ a, const double *__restrict__ b,
                    double *__restrict__ dot, int len_1d,
                    std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;

  auto t1 = clock::now();
  {
      dot[0] = 0.0;
      for (int i = 0; i < len_1d; ++i) {
        dot[0] += a[i] * b[i];
      }
  }
  auto t2 = clock::now();

  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
