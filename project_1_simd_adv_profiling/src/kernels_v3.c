#include "kernels_v3.h"
/* Separate translation unit, no LTO: every timed invocation remains observable.
 * Unit stride has its own loop; the stride study keeps the runtime stride fixed.
 * No alignment assumptions: offset is the only alignment variable. */
void saxpy_v3(const real *restrict x, real *restrict y, size_t n, size_t stride)
{
    if (stride == 1) {
        for (size_t i = 0; i < n; ++i) y[i] = (real)0.5 * x[i] + y[i];
    } else {
        for (size_t i = 0; i < n; ++i) y[i*stride] = (real)0.5 * x[i*stride] + y[i*stride];
    }
}
real dot_v3(const real *restrict x, const real *restrict y, size_t n)
{
    real sum = 0;
    for (size_t i = 0; i < n; ++i) sum += x[i] * y[i];
    return sum;
}
void stencil_v3(const real *restrict x, real *restrict y, size_t n)
{
    /* n outputs, x has n+2 input elements; out-of-place stencil. */
    for (size_t i = 0; i < n; ++i)
        y[i] = (real)0.25*x[i] + (real)0.5*x[i+1] + (real)0.25*x[i+2];
}
void copy_v3(const real *restrict x, real *restrict y, size_t n)
{
    for (size_t i = 0; i < n; ++i) y[i] = x[i];
}
