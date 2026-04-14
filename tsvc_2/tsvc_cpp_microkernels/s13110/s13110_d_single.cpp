#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ------------------------------------------------------------
// s13110_d_single: same pattern as s3110 (variant)
// ------------------------------------------------------------
void s13110_d_single(double *__restrict__ aa, double *__restrict__ bb, int len_2d, std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;

  auto t1 = clock::now();
  {
    auto idx = [len_2d](int i, int j) { return i * len_2d + j; };

    int xindex, yindex;
    double maxv = 0.0;
    double chksum = 0.0;
      maxv = aa[idx(0, 0)];
      xindex = 0;
      yindex = 0;
      for (int i = 0; i < len_2d; ++i) {
        for (int j = 0; j < len_2d; ++j) {
          double v = aa[idx(i, j)];
          if (v > maxv) {
            maxv = v;
            xindex = i;
            yindex = j;
          }
        }
      }
      chksum = maxv + static_cast<double>(xindex) + static_cast<double>(yindex);
      bb[0] = chksum;
  }
  auto t2 = clock::now();

  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
