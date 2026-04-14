#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// s332_f_single: first value greater than threshold (search loop with early exit)
void s332_f_single(const float *__restrict__ a, float *__restrict__ result,
                    int threshold, int len_1d,
                    std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;

  auto t1 = clock::now();
  {
    int index;
    float value;
      index = -2;
      value = -1.0f;
      for (int i = 0; i < len_1d; ++i) {
        if (a[i] > threshold) {
          index = i;
          value = a[i];
          break;
        }
      }
      result[0] = value + static_cast<float>(index);
  }
  auto t2 = clock::now();

  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
