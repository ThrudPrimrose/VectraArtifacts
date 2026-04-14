#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// -----------------------------------------------------------------------------
// Helpers (pure, small)
// -----------------------------------------------------------------------------
static inline float tsvc_mul_f_single(float a, float b) { return a * b; }

// -----------------------------------------------------------------------------
// %4.2f  s424_f_single
// -----------------------------------------------------------------------------
void s424_f_single(float *__restrict__ a, const float *__restrict__ flat,
                    float *__restrict__ xx, int len_1d,
                    std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;
  auto t1 = clock::now();

  // TSVC uses: vl = 63; xx = flat_2d_array + vl;
  // Here: caller passes xx already pointing to the shifted region.
    for (int i = 0; i < len_1d - 1; ++i) {
      xx[i + 1] = flat[i] + a[i];
    }

  auto t2 = clock::now();
  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
