#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// quasi_affine_reduce_odd_f: sum a[i] for i in 1.f.len_1d step 2
void quasi_affine_reduce_odd_f(const float *__restrict__ a, float *__restrict__ out, const int len_1d,
                                       std::int64_t * __restrict__ time_ns) {
  auto t1 = clock_highres::now();
  float acc = 0.0f;
  for (int i = 1; i < len_1d; i += 2) {
    acc += a[i];
  }
  out[0] = acc;
  auto t2 = clock_highres::now();
  time_ns[0] = std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
