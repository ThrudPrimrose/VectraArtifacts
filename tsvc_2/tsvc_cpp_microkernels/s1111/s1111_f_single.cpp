#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// s1111_f_single: a[2*i] = c[i]*b[i] + d[i]*b[i] + c[i]*c[i] + d[i]*b[i] + d[i]*c[i]
void s1111_f_single(float *__restrict__ a, const float *__restrict__ b,
                     const float *__restrict__ c, const float *__restrict__ d, const int len_1d,
                     std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;

  auto t1 = clock::now();
  {
    const int half = len_1d / 2;
      for (int i = 0; i < half; ++i) {
        const float bi = b[i];
        const float ci = c[i];
        const float di = d[i];
        a[2 * i] = ci * bi + di * bi + ci * ci + di * bi + di * ci;
      }
  }
  auto t2 = clock::now();

  std::int64_t ns =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
  time_ns[0] = ns;
}

} // extern "C"
