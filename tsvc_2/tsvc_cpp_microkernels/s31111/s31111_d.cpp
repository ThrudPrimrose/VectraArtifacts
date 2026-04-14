#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// ------------------------------------------------------------
// helper test() (used by s31111_d)
// ------------------------------------------------------------
double s31111_test_d(const double *__restrict__ A) {
  double s = 0.0;
  for (int i = 0; i < 4; i++)
    s += A[i];
  return s;
}
// ------------------------------------------------------------
// s31111_d
// ------------------------------------------------------------
void s31111_d(double *__restrict__ a, double *__restrict__ b,
                      int iterations, int len_1d, std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;

  auto t1 = clock::now();
  {
    for (int nl = 0; nl < 2000 * iterations; nl++) {
      double sum = 0.0;
      for (int base = 0; base < len_1d; base += 4)
        sum += s31111_test_d(&a[base]);

      b[0] = sum;
    }
  }

  auto t2 = clock::now();

  *time_ns =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
