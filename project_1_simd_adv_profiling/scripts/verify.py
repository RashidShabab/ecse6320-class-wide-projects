#!/usr/bin/env python3
"""Independent reference and memory-safety validation; not performance runs."""
import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def main():
    outputs=[]
    def run(cmd):
        r=subprocess.run(list(map(str,cmd)),cwd=ROOT,text=True,capture_output=True,check=True)
        outputs.append({"command":list(map(str,cmd)),"stdout":r.stdout,"stderr":r.stderr})
    for dtype in ["float32","float64"]:
        define=["-DDOUBLE"] if dtype=="float64" else []
        for mode in ["scalar","auto","native"]:
            exe=ROOT/"bin"/f"validate_{dtype}_{mode}"
            run(["gcc","-O2","-Wall","-Wextra","-Werror",*define,"src/validate_v3.c",ROOT/"bin"/f"{dtype}_{mode}.o","-lm","-o",exe])
            run([exe])
        exe=ROOT/"bin"/f"sanitize_{dtype}"
        run(["gcc","-O1","-g","-fsanitize=address,undefined","-fno-omit-frame-pointer",*define,"src/validate_v3.c","src/kernels_v3.c","-lm","-o",exe])
        run([exe])
    (ROOT/"env/evidence/validation.json").write_text(json.dumps(outputs,indent=2))
    print("PASS: all six optimized variants plus ASan/UBSan for both datatypes.")

if __name__=="__main__":main()
