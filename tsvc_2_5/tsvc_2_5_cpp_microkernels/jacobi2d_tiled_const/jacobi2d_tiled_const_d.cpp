#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// -------------------------------------------------------------------------
// Already-tiled stencils
// -------------------------------------------------------------------------

// jacobi2d_tiled_const_d: 2D 5-point Jacobi pre-tiled with constant tile size 64
void jacobi2d_tiled_const_d(double *__restrict__ b, const double *__restrict__ a, const int len_2d,
                                    std::int64_t * __restrict__ time_ns) {
  const int t = 64;
  auto t1 = clock_highres::now();
  for (int ii = 1; ii < len_2d - 1 - t; ii += t) {
    for (int jj = 1; jj < len_2d - 1 - t; jj += t) {
      for (int i = ii; i < ii + t; ++i) {
        for (int j = jj; j < jj + t; ++j) {
          b[i * len_2d + j] = 0.2 * (a[i * len_2d + j] + a[(i - 1) * len_2d + j] + a[(i + 1) * len_2d + j] +
                                     a[i * len_2d + (j - 1)] + a[i * len_2d + (j + 1)]);
        }
      }
    }
  }
  auto t2 = clock_highres::now();
  time_ns[0] = std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
