# Predictions recorded before the version 3 sweeps

1. Alignment: repeat the earlier aligned/+4-byte comparison in alternating order. Cache-resident AVX2 should be more sensitive to split accesses; DRAM differences may be obscured by variability. No claim that alignment eliminates all overhead.
2. Tail: compare N=64..71 and 4096..4103 with 64-byte aligned float32 arrays and unit stride. Normalize by actual N. Small loops may expose remainder and call overhead; the same tail should matter less at N near 4096. Disassembly, not timings alone, identifies cleanup instructions.
3. Stride: compare 1, 2, 4, 8 at fixed allocated span (L1, L2, DRAM). N=span/stride is the number of useful updates. This holds cache footprint approximately constant and changes useful work; report ns/update and useful bytes/s. Runtime stride may prevent vectorization, which is part of this access-pattern case, not proof that AVX2 cannot gather.
4. Kernels: SAXPY and out-of-place stencil should vectorize; strict dot reduction may retain serial accumulation even if multiplication uses packed instructions. This is a candidate verified negative case.
5. Locality and datatype: byte-matched float32/float64 working sets should show strongest SIMD advantage in cache, shrinking toward DRAM. Nominal 8-versus-4 AVX2 lanes need not translate to exactly 2x throughput.
6. Roofline: low-intensity SAXPY should be constrained by memory service for large arrays. An independent large-array copy measures effective stream bandwidth; it is a workload-dependent reference, not a physical DRAM traffic counter or universal bound.
7. Negative case: reproduce native versus scalar/auto comparisons rather than assuming the historical native DRAM slowdown persists. Report process-to-process spread.

All new benchmarks use separate translation units without LTO, so repeated calls cannot be hoisted or merged by interprocedural optimization. Existing versions and historical data remain separate. Hardware cycles are reported only if perf_event_open works; invariant TSC ticks are explicitly a different metric.
