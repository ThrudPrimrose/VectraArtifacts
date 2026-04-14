#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// s343_f_single: pack 2D aa into flat_2d_array based on bb > 0
void s343_f_single(const float *__restrict__ aa,
                    const float *__restrict__ bb,
                    float *__restrict__ flat_2d_array,
                    int len_2d, std::int64_t * __restrict__ time_ns) {
  auto t1 = clock_highres::now();

    int k = -1;
    for (int i = 0; i < len_2d; ++i) {
      for (int j = 0; j < len_2d; ++j) {
        int idx = j * len_2d + i;
        if (bb[idx] > 0.0f) {
          ++k;
          flat_2d_array[k] = aa[idx];
        }
      }
    }

  auto t2 = clock_highres::now();
  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
