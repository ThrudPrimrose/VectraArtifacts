#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// jacobi2d_double_tiled_const_f: 2D 5-point Jacobi with constant outer (64) and inner (8) tiles
void jacobi2d_double_tiled_const_f(float *__restrict__ b, const float *__restrict__ a, const int len_2d,
                                           std::int64_t * __restrict__ time_ns) {
  const int t1_v = 64;
  const int t2_v = 8;
  auto t1 = clock_highres::now();
  for (int ii = 1; ii < len_2d - 1 - t1_v; ii += t1_v) {
    for (int jj = 1; jj < len_2d - 1 - t1_v; jj += t1_v) {
      for (int iii = ii; iii < ii + t1_v; iii += t2_v) {
        for (int jjj = jj; jjj < jj + t1_v; jjj += t2_v) {
          for (int i = iii; i < iii + t2_v; ++i) {
            for (int j = jjj; j < jjj + t2_v; ++j) {
              b[i * len_2d + j] = 0.2f * (a[i * len_2d + j] + a[(i - 1) * len_2d + j] + a[(i + 1) * len_2d + j] +
                                         a[i * len_2d + (j - 1)] + a[i * len_2d + (j + 1)]);
            }
          }
        }
      }
    }
  }
  auto t2 = clock_highres::now();
  time_ns[0] = std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
