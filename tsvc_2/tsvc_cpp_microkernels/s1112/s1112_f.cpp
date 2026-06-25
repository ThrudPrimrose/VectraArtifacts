#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// s1112_f: reversed loop, a[i] = b[i] + 1
void s1112_f(float *__restrict__ a, const float *__restrict__ b,
                     const int iterations, const int len_1d,
                     std::int64_t * __restrict__ time_ns) {

  auto t1 = clock_highres::now();
  {
    
      for (int i = len_1d - 1; i >= 0; --i) {
        a[i] = b[i] + 1.0f;
      }
    
  }
  auto t2 = clock_highres::now();

  std::int64_t ns =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
  time_ns[0] = ns;
}

} // extern "C"
