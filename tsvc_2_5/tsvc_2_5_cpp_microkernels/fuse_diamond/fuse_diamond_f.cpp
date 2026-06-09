#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// fuse_diamond_f: t=a*a; u=t+1; v=t-1; out=u*v (fused diamond)
void fuse_diamond_f(float *__restrict__ out, const float *__restrict__ a, const int len_1d,
                            std::int64_t * __restrict__ time_ns) {
  auto t1 = clock_highres::now();
  for (int i = 0; i < len_1d; ++i) {
    float t = a[i] * a[i];
    out[i] = (t + 1.0f) * (t - 1.0f);
  }
  auto t2 = clock_highres::now();
  time_ns[0] = std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
