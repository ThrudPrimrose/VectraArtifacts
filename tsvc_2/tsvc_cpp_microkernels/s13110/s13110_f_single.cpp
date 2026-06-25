#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

static long idx_f_single(long i, long j, long n) { return i * n + j; }


// ------------------------------------------------------------
// s13110_f_single: same pattern as s3110 (variant)
// ------------------------------------------------------------
void s13110_f_single(float *__restrict__ aa, float *__restrict__ bb,
                      int iterations, int len_2d, std::int64_t * __restrict__ time_ns) {

  auto t1 = clock_highres::now();
  {

    int xindex, yindex;
    float maxv = 0.0f;
    float chksum = 0.0f;
    
      maxv = aa[idx_f_single(0, 0, len_2d)];
      xindex = 0;
      yindex = 0;
      for (int i = 0; i < len_2d; ++i) {
        for (int j = 0; j < len_2d; ++j) {
          float v = aa[idx_f_single(i, j, len_2d)];
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
  auto t2 = clock_highres::now();

  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
