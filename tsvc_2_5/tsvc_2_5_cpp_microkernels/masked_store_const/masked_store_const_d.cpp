#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// -------------------------------------------------------------------------
// Masked stores
// -------------------------------------------------------------------------

// masked_store_const_d: predicated store keyed on int mask
void masked_store_const_d(double *__restrict__ a, const double *__restrict__ b,
                                  const std::int64_t *__restrict__ mask, const int len_1d, std::int64_t * __restrict__ time_ns) {
  auto t1 = clock_highres::now();
  for (int i = 0; i < len_1d; ++i) {
    if (mask[i] > 0) {
      a[i] = b[i];
    }
  }
  auto t2 = clock_highres::now();
  time_ns[0] = std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
