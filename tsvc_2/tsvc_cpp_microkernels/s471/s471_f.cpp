#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// -----------------------------------------------------------------------------
// %4.7f  s471_f  (s471s_f is a dummy)
// -----------------------------------------------------------------------------
int s471s_f() { return 0; }

void s471_f(float *__restrict__ b, const float *__restrict__ c,
                    const float *__restrict__ d, const float *__restrict__ e,
                    float *__restrict__ x, int iterations, int len_1d,
                    std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;
  auto t1 = clock::now();

  int m = len_1d;
  for (int nl = 0; nl < iterations / 2; ++nl) {
    for (int i = 0; i < m; ++i) {
      x[i] = b[i] + d[i] * d[i];
      s471s_f();
      b[i] = c[i] + d[i] * e[i];
    }
  }

  auto t2 = clock::now();
  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
