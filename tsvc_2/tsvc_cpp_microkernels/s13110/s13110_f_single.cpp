#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ------------------------------------------------------------
// s13110_f_single: same pattern as s3110 (variant)
// ------------------------------------------------------------
void s13110_f_single(float *__restrict__ aa, float *__restrict__ bb, int len_2d, std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;

  auto t1 = clock::now();
  {
    auto idx = [len_2d](int i, int j) { return i * len_2d + j; };

    int xindex, yindex;
    float maxv = 0.0f;
    float chksum = 0.0f;
      maxv = aa[idx(0, 0)];
      xindex = 0;
      yindex = 0;
      for (int i = 0; i < len_2d; ++i) {
        for (int j = 0; j < len_2d; ++j) {
          float v = aa[idx(i, j)];
          if (v > maxv) {
            maxv = v;
            xindex = i;
            yindex = j;
          }
        }
      }
      chksum = maxv + static_cast<float>(xindex) + static_cast<float>(yindex);
      bb[0] = chksum;
  }
  auto t2 = clock::now();

  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
