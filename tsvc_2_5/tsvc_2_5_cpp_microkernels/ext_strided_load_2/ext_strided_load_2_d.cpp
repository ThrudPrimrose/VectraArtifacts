#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ext_strided_load_2_d: dst[i] = src[i * 2] * scale (constant-stride sibling)
void ext_strided_load_2_d(double *__restrict__ dst, const double *__restrict__ src, const double scale,
                                  const int len_1d, std::int64_t * __restrict__ time_ns) {
  auto t1 = clock_highres::now();
  for (int i = 0; i < len_1d; ++i) {
    dst[i] = src[i * 2] * scale;
  }
  auto t2 = clock_highres::now();
  time_ns[0] = std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
