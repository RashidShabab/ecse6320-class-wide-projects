#include <stddef.h>
#ifdef DOUBLE
typedef double real;
#else
typedef float real;
#endif
void saxpy_v3(const real *restrict x, real *restrict y, size_t n, size_t stride);
real dot_v3(const real *restrict x, const real *restrict y, size_t n);
void stencil_v3(const real *restrict x, real *restrict y, size_t n);
void copy_v3(const real *restrict x, real *restrict y, size_t n);
