# Targeted SIMD evidence

Generated with GCC 15.2.0 from `src/kernels_v3.c`; full build commands and object disassembly are saved under `env/evidence/`. These excerpts refer to kernel loops, not array initialization or reference checks.

| Build / path | Observed instructions | Interpretation |
|---|---|---|
| float32 scalar SAXPY | `mulss xmm0,xmm1`; `addss xmm0,DWORD PTR [...]` | Scalar arithmetic; an XMM register alone does not mean packed SIMD |
| float32 auto unit-stride SAXPY | `movups xmm0,XMMWORD PTR [...]`; `mulps xmm0,xmm1`; `addps xmm0,xmm2` | Four float32 lanes, SSE |
| float32 native unit-stride SAXPY | `vmovups ymm0,YMMWORD PTR [...]`; `vfmadd213ps ymm0,ymm1,YMMWORD PTR [...]` | Eight float32 lanes, AVX2/FMA |
| float64 native unit-stride SAXPY | `vmovupd ymm0,YMMWORD PTR [...]`; `vfmadd213pd ymm0,ymm1,YMMWORD PTR [...]` | Four float64 lanes |
| float32 native non-unit stride | `vmovss xmm0,DWORD PTR [...]`; `vfmadd213ss xmm0,xmm1,DWORD PTR [...]` | Scalar access path, despite native ISA flags |
| float32 native dot | `vmulps ymm1,ymm1,YMMWORD PTR [rdi+rax*1]` followed by repeated `vaddss xmm0,xmm0,...` and lane shuffles | Packed products, ordered scalar accumulation; not a parallel reduction |
| float32 native stencil | `vmulps ymm0,ymm2,YMMWORD PTR [...]`; `vfmadd231ps ymm0,ymm1,YMMWORD PTR [...]` twice | Eight outputs per packed body; neighbor streams overlap |

Selected GCC diagnostics for the native builds:

```text
src/kernels_v3.c:8:30: optimized: loop vectorized using 32 byte vectors
src/kernels_v3.c:8:30: optimized: loop vectorized using 16 byte vectors
src/kernels_v3.c:10:30: missed: couldn't vectorize loop
src/kernels_v3.c:16:26: optimized: loop vectorized using 32 byte vectors
src/kernels_v3.c:22:26: optimized: loop vectorized using 32 byte vectors
```

Line 8 is unit-stride SAXPY; line 10 is non-unit stride; line 16 is dot; line 22 is stencil. The dot report must be interpreted with its scalar accumulation instructions.

Native float32 SAXPY remainder handling includes `test r8b,0x7`, an XMM packed path and scalar `vfmadd...ss` cleanup. It uses no AVX-512 masking. The scalar variant has no packed multiply/add in either SAXPY branch. Inspect using:

```bash
objdump -d -Mintel --disassemble=saxpy_v3 bin/v3/float32_native.o
objdump -d -Mintel --disassemble=dot_v3 bin/v3/float32_native.o
objdump -d -Mintel --disassemble=stencil_v3 bin/v3/float32_native.o
```

The copy loop is recognized as a library copy and calls `memcpy`; its effective bandwidth is an independent stream reference whose implementation can differ from SAXPY.
