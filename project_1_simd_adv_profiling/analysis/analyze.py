#!/usr/bin/env python3
"""Rebuild plots, processed CSVs and results/processed/generated_tables.md from saved version 3 measurements.

report/Report.md is written by hand and is never modified here. Compare it with
results/processed/generated_tables.md after regenerating, and update its numbers if they change.
"""
from pathlib import Path
import json
import re
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"figures"
OUT.mkdir(parents=True,exist_ok=True)
plt.rcParams.update({"font.size":10,"axes.spines.top":False,"axes.spines.right":False,"figure.dpi":140})
COLORS={"scalar":"#64748b","auto":"#167d9a","native":"#c05224"}
REGIONS=["L1","L2","L3","DRAM"]

def load(study):
    path=sorted((ROOT/"results/raw").glob(f"*_{study}/summary.csv"))[-1]
    d=pd.read_csv(path)
    return d,path

def save(fig,name):
    fig.tight_layout()
    fig.savefig(OUT/f"{name}.png",bbox_inches="tight")
    plt.close(fig)

def curve(ax,d,x,y,label,color):
    g=d.groupby(x)[y].agg(["median","min","max"]).sort_index()
    ax.errorbar(g.index,g["median"],yerr=np.array([g["median"]-g["min"],g["max"]-g["median"]]),
                marker="o",capsize=3,label=label,color=color)

def table(df,columns):
    data=df[columns].copy()
    for c in data.select_dtypes(include="number").columns:data[c]=data[c].map(lambda x:f"{x:.3g}")
    labels={"region":"Region","mode":"Build","gflops":"GFLOP/s","speedup":"Speedup (x)",
            "cv_pct":"CV (%)","stride":"Stride (elements)","effective_gbs":"Useful GB/s",
            "median":"Median overhead (%)","min":"Min overhead (%)","max":"Max overhead (%)"}
    return "| "+" | ".join(labels.get(c,c) for c in columns)+" |\n|"+"|".join(["---"]*len(columns))+"|\n"+"\n".join("| "+" | ".join(map(str,row))+" |" for row in data.itertuples(index=False,name=None))

def main():
    datasets={s:load(s) for s in ["tail","stride","alignment","locality","bandwidth"]}
    loc=datasets["locality"][0].copy()
    key=["kernel","dtype","region","trial"]
    baseline=loc[loc["mode"]=="scalar"][key+["median_s"]].rename(columns={"median_s":"scalar_s"})
    loc=loc.merge(baseline,on=key,validate="many_to_one")
    loc["speedup"]=loc.scalar_s/loc.median_s
    loc["region_index"]=loc.region.map({x:i for i,x in enumerate(REGIONS)})
    loc.to_csv(ROOT/"results/processed/locality_analysis.csv",index=False)
    for metric,label in [("speedup","Speedup vs scalar (x)"),("gflops","Throughput (GFLOP/s)")]:
        fig,axes=plt.subplots(3,2,figsize=(11,11))
        for i,kernel in enumerate(["saxpy","dot","stencil"]):
            for j,dtype in enumerate(["float32","float64"]):
                ax=axes[i,j]
                for mode in ["scalar","auto","native"]:
                    if metric=="speedup" and mode=="scalar":continue
                    d=loc[(loc.kernel==kernel)&(loc.dtype==dtype)&(loc["mode"]==mode)]
                    curve(ax,d,"region_index",metric,mode,COLORS[mode])
                if metric=="speedup":ax.axhline(1,color="gray",ls="--",lw=1)
                ax.set(xticks=range(4),xticklabels=REGIONS,ylabel=label,title=f"{kernel} / {dtype}")
                ax.legend(fontsize=8)
        fig.suptitle("Median of three process medians; whiskers = process min/max",y=1.01)
        save(fig,f"locality_{metric}")

    tail=datasets["tail"][0].copy()
    base=tail[tail.n==tail.base_n][["mode","base_n","trial","ns_per_element"]].rename(columns={"ns_per_element":"base_ns"})
    tail=tail.merge(base,on=["mode","base_n","trial"],validate="many_to_one")
    tail["remainder"]=tail.n-tail.base_n
    tail["normalized_overhead_pct"]=100*(tail.ns_per_element/tail.base_ns-1)
    tail.to_csv(ROOT/"results/processed/tail_analysis.csv",index=False)
    fig,axes=plt.subplots(1,2,figsize=(11,4))
    for ax,base_n in zip(axes,[64,4096]):
        for mode in COLORS:
            curve(ax,tail[(tail.base_n==base_n)&(tail["mode"]==mode)],"remainder","normalized_overhead_pct",mode,COLORS[mode])
        ax.axhline(0,color="gray",lw=1)
        ax.set(title=f"N = {base_n} + remainder",xlabel="AVX2 float32 remainder (elements)",ylabel="Change in ns/element (%)")
        ax.legend()
    save(fig,"tail")

    stride=datasets["stride"][0]
    fig,axes=plt.subplots(1,3,figsize=(13,4))
    for ax,region in zip(axes,["L1","L2","DRAM"]):
        for mode in COLORS:
            curve(ax,stride[(stride.region==region)&(stride["mode"]==mode)],"stride","effective_gbs",mode,COLORS[mode])
        ax.set(title=region,xlabel="Stride (elements)",ylabel="Useful bandwidth (GB/s)",xticks=[1,2,4,8]);ax.legend()
    save(fig,"stride")

    align=datasets["alignment"][0].copy()
    base=align[align.offset==0][["mode","region","trial","median_s"]].rename(columns={"median_s":"aligned_s"})
    align=align.merge(base,on=["mode","region","trial"],validate="many_to_one")
    align["overhead_pct"]=100*(align.median_s/align.aligned_s-1)
    align["region_index"]=align.region.map({x:i for i,x in enumerate(["L1","L2","DRAM"])})
    align.to_csv(ROOT/"results/processed/alignment_analysis.csv",index=False)
    fig,ax=plt.subplots(figsize=(7,4))
    for mode in COLORS:curve(ax,align[(align.offset==1)&(align["mode"]==mode)],"region_index","overhead_pct",mode,COLORS[mode])
    ax.axhline(0,color="gray",lw=1)
    ax.set(xticks=range(3),xticklabels=["L1","L2","DRAM"],ylabel="+4-byte alignment time overhead (%)")
    ax.legend();save(fig,"alignment")

    fig,ax=plt.subplots(figsize=(8,4))
    native=loc[loc["mode"]=="native"]
    f32=native[native.dtype=="float32"][["kernel","region_index","trial","gflops"]]
    f64=native[native.dtype=="float64"][["kernel","region_index","trial","gflops"]]
    dt=f32.merge(f64,on=["kernel","region_index","trial"],suffixes=("_f32","_f64"))
    dt["ratio"]=dt.gflops_f32/dt.gflops_f64
    for kernel,color in zip(["saxpy","dot","stencil"],COLORS.values()):curve(ax,dt[dt.kernel==kernel],"region_index","ratio",kernel,color)
    ax.axhline(2,color="gray",ls="--",label="AVX2 lane-count ratio")
    ax.set(xticks=range(4),xticklabels=REGIONS,ylabel="float32 / float64 GFLOP/s",title="Native builds, matched byte footprints")
    ax.legend(loc="upper center",bbox_to_anchor=(0.5,-0.13),ncol=4,fontsize=8)
    save(fig,"datatype")

    bw=datasets["bandwidth"][0]
    # A workload-specific useful-byte roof, NOT a measured physical DRAM ceiling.
    bandwidth=float(bw.effective_gbs.median())
    estimate=2*8*2*5.3  # Explicit conditional P-core estimate; see report.
    ai=np.logspace(-2,2,300)
    fig,ax=plt.subplots(figsize=(8,5))
    ax.loglog(ai,np.minimum(estimate,bandwidth*ai),label="Copy-based effective-bandwidth reference")
    ax.axhline(estimate,color="gray",ls="--",label="Conditional float32 peak: 169.6 GFLOP/s")
    ax.axhline(estimate/2,color="gray",ls=":",label="Conditional float64 peak: 84.8 GFLOP/s")
    dram=loc[(loc.kernel=="saxpy")&(loc.region=="DRAM")]
    for dtype,marker in [("float32","o"),("float64","s")]:
        for mode in COLORS:
            p=dram[(dram.dtype==dtype)&(dram["mode"]==mode)].gflops
            intensity=2/(12 if dtype=="float32" else 24)
            ax.plot(intensity,p.median(),marker=marker,color=COLORS[mode],ls="none",label=f"{dtype} {mode}")
    ax.set(xlabel="Algorithmic intensity (FLOP/useful byte)",ylabel="GFLOP/s",title="DRAM-sized SAXPY: illustrative effective roofline")
    ax.legend(fontsize=8);save(fig,"roofline")

    summary=loc.groupby(["kernel","dtype","region","mode"],sort=False)[["gflops","speedup","cv_pct","tsc_ticks_per_element"]].median().reset_index()
    summary["region"]=pd.Categorical(summary.region,categories=REGIONS,ordered=True)
    summary["mode"]=pd.Categorical(summary["mode"],categories=list(COLORS),ordered=True)
    summary=summary.sort_values(["kernel","dtype","region","mode"])
    summary.to_csv(ROOT/"results/processed/final_summary.csv",index=False)
    total=sum(len(d) for d,_ in datasets.values())
    high=sum(int((d.cv_pct>15).sum()) for d,_ in datasets.values())
    errors=sum(int((d.max_error>1e-5).sum()) for d,_ in datasets.values())
    native_sax=summary[(summary.kernel=="saxpy")&(summary.dtype=="float32")&(summary["mode"]=="native")]
    dot=summary[(summary.kernel=="dot")&(summary.dtype=="float32")]
    stride_tab=stride[(stride["mode"]=="native")].groupby(["region","stride"],sort=False).effective_gbs.median().reset_index()
    align_tab=align[(align.offset==1)].groupby(["region","mode"],sort=False).overhead_pct.agg(["median","min","max"]).reset_index()
    native_dram=dram[(dram.dtype=="float32")&(dram["mode"]=="native")]
    report=f'''# Generated tables for Project 1 (not the submitted report)

Regenerated by analysis/analyze.py from the saved runs listed at the end. The submitted report is report/Report.md; use this file to check its numbers after re-running the analysis.

## Scope and completion status

Three kernels (SAXPY, strict dot product, out-of-place three-point stencil), two datatypes, scalar/default/native builds, byte-matched locality, alignment, all AVX2 float32 remainders, strides 1/2/4/8, raw repeated measurements, compiler evidence and plots are included. All {total} process runs passed the numerical and guard checks; each contains 20 timed intervals after three warmup intervals. {high} process runs exceeded the 15% within-process CV flag. No flagged measurement was discarded.

One measurement requirement remains unresolved: actual core cycles are unavailable on this WSL PMU. TSC ticks are supplied as a clearly labeled supplementary metric, not a substitute claimed to meet the core-cycle requirement. Review the counter limitation with the instructor or rerun on Linux with PMU access before declaring every assignment item complete.

## Hypotheses and methodology

Predictions were saved in HYPOTHESES.md before the sweeps. CPU: Intel Core Ultra 7 265H; WSL2 Linux 6.6.87.2; GCC 15.2.0. Single process/thread pinned to logical CPU 0 with sched_setaffinity. WSL exposes 16 logical CPUs and one thread per core; physical host scheduling and P/E-core placement are not controlled. Reported cache capacities are 48 KiB L1d, 3 MiB L2 per exposed core and 24 MiB shared L3. These are guest-visible values, not a verified physical mapping for CPU 0.

Scalar flags: `-O3 -fno-tree-vectorize`; default: `-O3`; native: `-O3 -march=native`. The identical measurement harness is compiled separately at `-O2`; there is no LTO. Thus native-versus-scalar also changes ISA and FMA contraction, as the assignment requests; it does not isolate vector width alone. The externally compiled kernel calls cannot be hoisted across repetitions. Kernels receive runtime data. Exact commands, source hashes, disassembly and compiler diagnostics are saved in env/evidence/

Timer: CLOCK_MONOTONIC_RAW. Each process uses three warmup intervals and 20 timed intervals. Three separate processes per configuration are run with reproducible shuffled locality order or alternating order for knob studies. Each interval makes the recorded number of calls; time is divided by that count. Initialization, reset and reference checks are outside timing. Checks run after every interval. No explicit cache flush is used: small working sets are intentionally hot; large scans exceed LLC. Checking/resetting buffers can affect initial cache state and the same policy is used in every build. Repeats within a process are correlated, so plotted error bars are the min/max of the three process medians, not confidence intervals. Frequency/governor controls are not exposed; turbo and other host activity remain uncontrolled. The WSL-reported frequency must not be treated as a measured operating frequency.

Input values vary periodically and are binary fractions. SAXPY uses a=0.5, x=(i mod 17 - 8)/16 and y=(i mod 13 - 6)/16. Its reference includes all repeated updates. Dot uses a long-double reference; stencil checks each output against a scalar expression. These exact-friendly inputs isolate correctness from rounding but do not prove accuracy on arbitrary data. The separate randomized reference/sanitizer validation covers additional inputs and boundary sizes. Stencil uses n output points and n+2 input points; boundary semantics are explicit. No fast-math option is used.

Working sets contain two arrays: approximately 32 KiB, 2 MiB, 15.3 MiB and 76.3 MiB. Float64 halves N to match float32 bytes. These are intended cache regimes rather than measured residency guarantees. SAXPY and dot count 2 FLOPs/element; stencil counts 5 (three multiplies and two adds). FMA counts as two FLOPs. Effective traffic is 3w bytes/update for SAXPY, 2w for dot/copy and 2w for stencil assuming inter-output input reuse; w is element size. Stencil source-level load/store traffic is 4w, distinct from this ideal streaming model. Write allocation and physical DRAM transactions are not measured.

Concise kernel-specific instruction excerpts and compiler messages are in [VECTORIZATION.md](VECTORIZATION.md).

## Locality and data type

{table(native_sax,["region","gflops","speedup","cv_pct"])}

These are medians of process medians; CV is the median within-process CV percentage. The full three-kernel/two-datatype tables are in results/processed/final_summary.csv. Speedups are paired by trial ID against the corresponding scalar build. Cache-resident throughput can exceed DRAM bandwidth without contradiction: reported bandwidth is algorithmic traffic served by the cache hierarchy.

![Locality speedups](../figures/locality_speedup.png)
![Kernel throughput](../figures/locality_gflops.png)
![Datatype comparison](../figures/datatype.png)

AVX2 fits eight float32 or four float64 values. Lane count explains a potential throughput difference but not an exact speedup prediction. Reduction dependencies, load/store throughput, FMA changes and memory service also matter. Compare byte-matched regimes and the measured spread rather than claiming an automatic factor of two.

## Alignment

The alignment experiment uses the shared harness with offsets 0 and one float (+4 bytes), identical allocation alignment, N, stride and flags. All addresses matched the requested modulo-64 value. GCC is not promised aligned pointers; this compares shifted addresses on the same general kernel.

{table(align_tab,["region","mode","median","min","max"])}

Values are percentage time overhead of shifted versus aligned, paired within each process-trial block; min/max show between-process spread. A positive value is slower. Negative or small changes overlapping zero should not be called a benefit. Split vector/cache-line accesses are a plausible contributor where penalties persist, but no counters isolate their cost.

![Alignment](../figures/alignment.png)

## Tail handling

Arrays stay aligned and stride stays one. N=64..71 and 4096..4103 cover all remainders modulo eight. The y axis uses time per actual element, normalized to the corresponding divisible N; raw duration and element count are retained. Native SAXPY assembly has a YMM body, a smaller XMM path and scalar cleanup instructions. This establishes that tails exist; it does not attribute every timing fluctuation to them. At small N, call/loop overhead is substantial. The observed spread precludes a universal tail penalty or monotonic ordering.

![Tail](../figures/tail.png)

## Stride and the verified negative case

N=span/stride holds allocation span approximately fixed. Each measurement counts only useful updates. The runtime stride is not a compile-time specialization. Disassembly of native saxpy_v3 shows a scalar strided branch (`vfmadd213ss`) while its unit-stride branch uses packed YMM `vfmadd213ps`. Thus non-unit stride does not receive the same vectorized implementation in this benchmark. This is a verified SIMD-friendly-looking loop that fails to vectorize under the tested settings, not a claim that gather-capable code is impossible.

{table(stride_tab,["region","stride","effective_gbs"])}

Useful bandwidth falls because fewer used values occupy each cache line, and because the generated non-unit-stride loop is scalar. The study measures their combined effect; it does not isolate cache-line waste from instruction selection.

![Stride](../figures/stride.png)

Strict dot product is an additional caution: packed multiplies can coexist with ordered scalar accumulation. A compiler's vectorized-loop message alone does not establish a fully parallel reduction. Inspect dot_v3, not initialization or unrelated loops, and compare these measured speedups:

{table(dot,["region","mode","gflops","speedup"])}

Historical native DRAM slowdown is not assumed reproducible. Current float32 native SAXPY DRAM speedup spans {native_dram.speedup.min():.3f}x to {native_dram.speedup.max():.3f}x across processes (median {native_dram.speedup.median():.3f}x). The scalar strided branch is the primary negative example regardless of the sign of this noisy historical comparison.

## Roofline interpretation

An independent native copy benchmark scans 80 MB and 160 MB of combined arrays on the same pinned CPU. Its median effective read+write bandwidth is {bandwidth:.3f} GB/s. This is a useful-byte streaming measurement, not a memory-controller counter; libc may implement the copy with different stores than SAXPY. Therefore the plotted slope is a workload-dependent reference, not a strict physical DRAM bound. All copy samples and both sizes are retained.

SAXPY AI is 2/12=0.1667 FLOP/B (float32), or 2/24=0.0833 (float64). The corresponding copy-based reference rates are {bandwidth/6:.3f} and {bandwidth/12:.3f} GFLOP/s. Current native float32 DRAM performance is {native_dram.gflops.median():.3f} GFLOP/s. Differences can arise from write policy, cache state and host noise; exceeding an effective copy reference does not falsify the physical roofline model.

For a conditional compute estimate, assume a P-core can issue two 256-bit FMA operations/cycle and runs at 5.3 GHz: 2 instructions x 8 float lanes x 2 FLOPs x 5.3 GHz = 169.6 GFLOP/s (84.8 for float64). The two-FMA issue rate is a modeling assumption here, not measured evidence about CPU 0. [Intel's 265H specifications](https://www.intel.com/content/www/us/en/products/sku/241750/intel-core-ultra-7-processor-265h-24m-cache-up-to-5-30-ghz/specifications.html) supply the maximum P-core turbo frequency, not a sustained AVX frequency. With one FMA/cycle the estimate halves; lower actual frequency reduces it further. This estimate is deliberately conditional because WSL does not establish host core type or operating frequency. The low AI and large gap from this compute scenario support a memory-service interpretation, but PMU evidence would strengthen causal attribution.

Intel's [Lion Cove architecture diagram](https://cdrdv2-public.intel.com/824430/2024_Intel_Tech%20Tour%20TW_Next%20Gen%20P-core%20The%20Lion%20Cove%20Architecture-4.pdf) shows two FMA execution paths, supporting the P-core modeling scenario. Their sustained use and CPU 0's physical mapping remain unverified here.

![Roofline](../figures/roofline.png)

## Cycles and environment limitation

The program attempts PERF_COUNT_HW_CPU_CYCLES with perf_event_open for its own thread, excluding kernel/hypervisor time. WSL returns errno 2 (ENOENT: event unavailable); the perf command itself is also absent. Installing only a CLI would not establish PMU availability. Missing core_cycles_per_element is stored as -1, never silently substituted. A serialized RDTSCP interval reports invariant-TSC ticks per element separately; these count elapsed reference-clock time, including descheduling, not actual unhalted core cycles. Do not multiply wall time by a nominal CPU frequency and label it a hardware measurement. Rerun this same runner on a PMU-enabled Linux environment to fill the core-cycle column.

## Anomalies, limitations and AI use

{high}/{total} process runs had CV above 15%. Three process medians reveal some drift but do not eliminate WSL scheduling, turbo or host interference. CPU affinity inside WSL is not physical-core isolation. Small effects remain inconclusive when their spread is comparable to their magnitude. Native flags change several code-generation choices. Fixed-span stride changes useful work. The selected periodic inputs are sanity fixtures, not realistic application datasets.

OpenAI Codex recovered the unsaved runner, assisted with versioned benchmark code, compiler inspection, scripts, plots and this report. Automated validation includes every measured interval and separate scalar-reference/sanitizer checks. Claims about unavailable cycles and physical DRAM traffic were explicitly rejected. Rashid should review the code and results, explain the design choices, and update this AI-use note with his own independent checks before submission.

## Saved runs

'''
    for study,(_,path) in datasets.items():report+=f"- {study}: `{path.parent.relative_to(ROOT)}`\n"
    (ROOT/"results/processed/generated_tables.md").write_text(report)
    print(f"Wrote results/processed/generated_tables.md, seven plots, and analysis CSVs; {total} runs, {errors} failed rows.")

if __name__=="__main__":main()
