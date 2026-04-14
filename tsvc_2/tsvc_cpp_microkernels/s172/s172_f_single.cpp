#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ------------------------------------------------------------
// s172_f_single
// ------------------------------------------------------------
void s172_f_single(float *__restrict__ a, const float *__restrict__ b, const int len_1d, const int n1,
                    const int n3, std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;

  auto t1 = clock::now();
  {
      for (int i = n1 - 1; i < len_1d; i += n3) {
        a[i] += b[i];
      }
  }

  auto t2 = clock::now();
  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
