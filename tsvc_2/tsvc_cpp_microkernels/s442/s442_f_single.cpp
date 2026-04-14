#include <chrono>
#include <cstdint>
#include <cmath>
using clock_highres = std::chrono::high_resolution_clock;

extern "C" {

// -----------------------------------------------------------------------------
// %4.4f  s442_f_single
// -----------------------------------------------------------------------------
void s442_f_single(float *__restrict__ a, const float *__restrict__ b,
                    const float *__restrict__ c, const float *__restrict__ d,
                    const float *__restrict__ e, const int * __restrict__ indx, int len_1d, std::int64_t * __restrict__ time_ns) {
  using clock = std::chrono::high_resolution_clock;
  auto t1 = clock::now();

    for (int i = 0; i < len_1d; ++i) {
      switch (indx[i]) {
      case 1:
        a[i] += b[i] * b[i];
        break;
      case 2:
        a[i] += c[i] * c[i];
        break;
      case 3:
        a[i] += d[i] * d[i];
        break;
      case 4:
        a[i] += e[i] * e[i];
        break;
      default:
        break;
      }
    }

  auto t2 = clock::now();
  time_ns[0] =
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count();
}

} // extern "C"
