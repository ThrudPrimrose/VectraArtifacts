#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// move_if_data_dep_nest_f: data-dependent guard cond[i] in the MIDDLE of a 2D nest
void move_if_data_dep_nest_f(float *__restrict__ out, const float *__restrict__ src,
                                     const float *__restrict__ cond, const int len_2d, std::int64_t * __restrict__ time_ns) {
  auto t1 = clock_highres::now();
  for (int i = 0; i < len_2d; ++i) {
    if (cond[i] > 0.0f) {
      for (int j = 0; j < len_2d; ++j) {
        out[i * len_2d + j] = src[i * len_2d + j] * 2.0f;
      }
    }
  }
  auto t2 = clock_highres::now();
  time_ns[0] = std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
