#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// s123_f_single: induction variable under an if
void s123_f_single(float *__restrict__ a, const float *__restrict__ b,
                    const float *__restrict__ c, const float *__restrict__ d,
                    const float *__restrict__ e,
                    const int len_1d, std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;
  auto t1 = clock::now();
  {
    int j;
      j = -1;
      for (int i = 0; i < (len_1d / 2); i++) {
        j++;
        a[j] = b[i] + d[i] * e[i];
        if (c[i] > 0.0f) {
          j++;
          a[j] = c[i] + d[i] * e[i];
        }
      }
  }
  auto t2 = clock::now();
  std::int64_t ns =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
  time_ns[0] = ns;
}

} // extern "C"
