#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// s115_f_single: triangular saxpy loop
void s115_f_single(float *__restrict__ a, const float *__restrict__ aa, const int len_2d,
                    std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;
  auto t1 = clock::now();
  {
      for (int j = 0; j < len_2d; j++) {
        for (int i = j + 1; i < len_2d; i++) {
          a[i] -= aa[j * len_2d + i] * a[j];
        }
      }
  }
  auto t2 = clock::now();
  std::int64_t ns =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
  time_ns[0] = ns;
}

} // extern "C"
