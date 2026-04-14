#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// s1115_f: triangular saxpy loop variant
void s1115_f(float *__restrict__ aa, const float *__restrict__ bb,
                     const float *__restrict__ cc, const int iterations,
                     const int len_2d, std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;
  auto t1 = clock::now();
  {
    for (int nl = 0; nl < 100 * (iterations / len_2d); nl++) {
      for (int i = 0; i < len_2d; i++) {
        for (int j = 0; j < len_2d; j++) {
          aa[i * len_2d + j] =
              aa[i * len_2d + j] * cc[j * len_2d + i] + bb[i * len_2d + j];
        }
      }
    }
  }
  auto t2 = clock::now();
  std::int64_t ns =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
  time_ns[0] = ns;
}

} // extern "C"
