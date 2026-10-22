#!/usr/bin/env python3
"""Build and run the final single-threaded SIMD experiments."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import random
import statistics as st
import subprocess
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
FLAGS = {
    "scalar": ["-O3", "-fno-tree-vectorize"],
    "auto": ["-O3"],
    "native": ["-O3", "-march=native"],
}
REGIONS = [("L1", 4096, 5000), ("L2", 262144, 30),
           ("L3", 2000000, 3), ("DRAM", 10000000, 1)]

def call(cmd):
    return subprocess.run([str(x) for x in cmd], cwd=ROOT, check=True,
                          text=True, capture_output=True).stdout

def build():
    out = ROOT / "bin"
    out.mkdir(parents=True, exist_ok=True)
    evidence = ROOT / "env/evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    commands = []
    for dtype in ("float32", "float64"):
        define = ["-DDOUBLE"] if dtype == "float64" else []
        harness = out / f"harness_{dtype}.o"
        cmd = ["gcc", "-O2", "-Wall", "-Wextra", "-Werror", *define,
               "-c", "src/bench_v3.c", "-o", harness]
        call(cmd); commands.append(list(map(str, cmd)))
        for mode, flags in FLAGS.items():
            stem = f"{dtype}_{mode}"
            obj = out / f"{stem}.o"
            report = evidence / f"{stem}.vec.txt"
            report.write_text("")
            cmd = ["gcc", *flags, "-Wall", "-Wextra", "-Werror", *define,
                   f"-fopt-info-vec-all={report}", "-c", "src/kernels_v3.c", "-o", obj]
            call(cmd); commands.append(list(map(str, cmd)))
            cmd = ["gcc", harness, obj, "-lm", "-o", out / stem]
            call(cmd); commands.append(list(map(str, cmd)))
            (evidence / f"{stem}.asm.txt").write_text(call(["objdump", "-dr", "-Mintel", obj]))
    (evidence / "build_commands.json").write_text(json.dumps(commands, indent=2))
    print("Built six variants; vectorization reports and disassembly saved.", flush=True)

def environment(path):
    info = {"utc": datetime.now(timezone.utc).isoformat(), "flags": FLAGS,
            "warmups": 3, "timer": "CLOCK_MONOTONIC_RAW", "threads": 1,
            "sources_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in [ROOT/"scripts/run.py", *sorted(p for p in (ROOT/"src").iterdir() if p.suffix in {".c", ".h"})]}}
    for name, cmd in {"lscpu": ["lscpu"], "kernel": ["uname", "-a"],
                      "gcc": ["gcc", "--version"], "affinity": ["taskset", "-pc", str(os.getpid())]}.items():
        info[name] = call(cmd)
    for name in ["/proc/cpuinfo", "/proc/sys/kernel/perf_event_paranoid",
                 "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor",
                 "/sys/devices/system/cpu/smt/active"]:
        p = Path(name)
        info[name] = p.read_text() if p.exists() else "not exposed"
    path.write_text(json.dumps(info, indent=2))

def cases(study):
    result = []
    def add(kernel, dtype, mode, region, n, inner, stride=1, offset=0, base_n=0):
        result.append(dict(study=study,kernel=kernel,dtype=dtype,mode=mode,
                           region=region,n=n,inner=inner,stride=stride,offset=offset,base_n=base_n))
    if study == "locality":
        for kernel in ["saxpy", "dot", "stencil"]:
            for dtype in ["float32", "float64"]:
                for region,n,inner in REGIONS:
                    for mode in FLAGS:
                        add(kernel,dtype,mode,region,n//(2 if dtype=="float64" else 1),inner)
    elif study == "tail":
        for base in [64,4096]:
            for rem in range(8):
                for mode in FLAGS:
                    add("saxpy","float32",mode,f"N{base}",base+rem,50000 if base==64 else 5000,base_n=base)
    elif study == "stride":
        for region,span,inner in [REGIONS[0],REGIONS[1],REGIONS[3]]:
            for stride in [1,2,4,8]:
                for mode in FLAGS:
                    add("saxpy","float32",mode,region,span//stride,inner,stride)
    elif study == "alignment":
        for region,n,inner in [REGIONS[0],REGIONS[1],REGIONS[3]]:
            for mode in FLAGS:
                for offset in [0,1]:
                    add("saxpy","float32",mode,region,n,inner,offset=offset)
    elif study == "bandwidth":
        for n in [10000000,20000000]:
            add("copy","float32","native",f"{8*n/1e6:g}MB",n,2)
    return result

def run(study, trials, cpu):
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    dest=ROOT/"results/raw"/f"{stamp}_{study}"
    dest.mkdir(parents=True)
    environment(dest/"environment.json")
    (dest/"hypotheses.md").write_text((ROOT/"report/HYPOTHESES.md").read_text())
    matrix=cases(study)
    (dest/"plan.json").write_text(json.dumps({"cpu":cpu,"trials":trials,"cases":matrix},indent=2))
    raw=dest/"raw.jsonl"
    for trial in range(trials):
        # Alternating order for paired studies; reproducibly shuffled locality cases.
        order=list(matrix)
        if study=="locality": random.Random(6320+trial).shuffle(order)
        elif trial%2: order.reverse()
        for i,c in enumerate(order):
            cmd=[ROOT/"bin"/f"{c['dtype']}_{c['mode']}", c["kernel"], c["n"],c["inner"],c["stride"],c["offset"],20,cpu]
            output=call(cmd)
            r=json.loads(output)
            assert r["max_error"]<=1e-5 and r["guards_ok"]==1
            assert r["x_mod64"]==r["y_mod64"]==c["offset"]*r["itemsize"]%64
            r.update(c);r.update(trial=trial,cpu=cpu,command=list(map(str,cmd)))
            with raw.open("a") as f:f.write(json.dumps(r)+"\n")
            if i%6==0: print(f"{study}: trial {trial+1}/{trials}, case {i+1}/{len(order)}",flush=True)
    summarize(dest)
    print(f"RESULT_DIR={dest}",flush=True)
    return dest

def summarize(dest):
    rows=[]
    for line in (dest/"raw.jsonl").read_text().splitlines():
        r=json.loads(line); samples=r.pop("samples");r.pop("command")
        times=[s["seconds"] for s in samples]
        r.update(median_s=st.median(times),mean_s=st.mean(times),stddev_s=st.pstdev(times),
                 min_s=min(times),max_s=max(times),cv_pct=100*st.pstdev(times)/st.mean(times),
                 tsc_ticks_per_element=st.median(s["tsc_ticks_per_element"] for s in samples),
                 core_cycles_per_element=st.median(s["core_cycles_per_element"] for s in samples))
        flops={"saxpy":2,"dot":2,"stencil":5,"copy":0}[r["kernel"]]
        # Stencil ideal reuse model: input stream + output stream, not 3 distinct DRAM reads.
        useful_bytes={"saxpy":3,"dot":2,"stencil":2,"copy":2}[r["kernel"]]*r["itemsize"]
        r.update(ns_per_element=r["median_s"]*1e9/r["n"],
                 gflops=flops*r["n"]/r["median_s"]/1e9,
                 effective_gbs=useful_bytes*r["n"]/r["median_s"]/1e9,
                 footprint_bytes=2*(r["n"]*r["stride"]+2)*r["itemsize"],
                 warning="HIGH_VARIABILITY" if r["cv_pct"]>15 else "")
        rows.append(r)
    with (dest/"summary.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("command",choices=["build","tail","stride","alignment","locality","bandwidth"])
    p.add_argument("--trials",type=int,default=3)
    p.add_argument("--cpu",type=int,default=0)
    args=p.parse_args()
    if args.command=="build":build()
    else:
        if args.trials<1:p.error("trials must be positive")
        run(args.command,args.trials,args.cpu)

if __name__=="__main__":main()
