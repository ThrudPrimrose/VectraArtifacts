#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ============================================================================
// s222_f_single  (recurrence in middle of vectorizable ops)
// ============================================================================
void s222_f_single(float *__restrict__ a, float *__restrict__ b,
                    const float *__restrict__ c, float *__restrict__ e, const int len_1d,
                    std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;

  auto t1 = clock::now();
  {
      for (int i = 1; i < len_1d; ++i) {
        a[i] += b[i] * c[i];
        e[i] = e[i - 1] * e[i - 1];
        a[i] -= b[i] * c[i];
      }
  }

  auto t2 = clock::now();
  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
