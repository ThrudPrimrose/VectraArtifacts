#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// fission_gather_2body_f: b[i] = a[idx[i]]; e[i] = c[idx[i]] (two independent gathers)
void fission_gather_2body_f(float *__restrict__ b, float *__restrict__ e, const float *__restrict__ a,
                                    const float *__restrict__ c, const std::int64_t *__restrict__ idx,
                                    const int len_1d, std::int64_t * __restrict__ time_ns) {
  auto t1 = clock_highres::now();
  for (int i = 0; i < len_1d; ++i) {
    b[i] = a[idx[i]];
    e[i] = c[idx[i]];
  }
  auto t2 = clock_highres::now();
  time_ns[0] = std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
