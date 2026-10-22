#!/usr/bin/env python3
"""Build report/Report.tex and report/Report.pdf from report/Report.md.

Requires pandoc and pdflatex. Run from anywhere:  python3 scripts/build_report.py
Figures are copied from figures/ into report/p2_report_figures/ first.
"""
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REP = ROOT / "report"
FIGS = REP / "p2_report_figures"

PREAMBLE = r"""\documentclass[10pt,letterpaper]{article}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{textcomp}
\usepackage{amsmath,amssymb}
\usepackage[margin=0.7in]{geometry}
\usepackage{graphicx,longtable,booktabs,array,calc}
\usepackage{fvextra}
\usepackage[hidelinks]{hyperref}
\usepackage[expansion=false]{microtype}
\usepackage{etoolbox}
\usepackage{caption}
\usepackage{float}
\floatplacement{figure}{H}
\captionsetup{justification=centering,singlelinecheck=false,labelformat=empty,font=it}
\setlength{\LTpre}{4pt}
\setlength{\LTpost}{6pt}
\setcounter{tocdepth}{2}
\setcounter{secnumdepth}{0}
\renewcommand{\contentsname}{Table of contents}
\hypersetup{pdftitle={Project 2: Cache \& Memory Performance Profiling},pdfauthor={Rashid Shabab}}
\widowpenalty=10000
\clubpenalty=10000
\setlength{\parindent}{0pt}
\setlength{\parskip}{6pt}
\setlength{\tabcolsep}{4pt}
\renewcommand{\arraystretch}{1.18}
\emergencystretch=3em
\AtBeginEnvironment{longtable}{\footnotesize}
\AtBeginEnvironment{Highlighting}{\footnotesize}
\providecommand{\tightlist}{\setlength{\itemsep}{0pt}\setlength{\parskip}{0pt}}
\providecommand{\pandocbounded}[1]{#1}
\usepackage{fancyvrb}
\DefineVerbatimEnvironment{verbatim}{Verbatim}{fontsize=\footnotesize,breaklines}
\begin{document}
\begin{titlepage}
\thispagestyle{empty}
\centering
\vspace*{1.2in}
{\Large\bfseries ECSE 6320\par}
\vspace{0.3in}
{\Large Advanced Computer Systems\par}
\vspace{0.9in}
{\LARGE\bfseries Project 2: Cache \& Memory Performance Profiling\par}
\vspace{0.9in}
{\large Submitted by Rashid Shabab\par}
\vfill
\end{titlepage}
\setcounter{page}{2}
\tableofcontents
\clearpage
"""

# characters pdflatex cannot typeset directly -> LaTeX equivalents
UNICODE = {"→": r"$\rightarrow$", "≈": r"$\approx$", "×": r"$\times$", "·": r"$\cdot$", "−": r"$-$",
           "≫": r"$\gg$", "…": r"\ldots{}", "–": "--", "—": "---", "≤": r"$\leq$", "≥": r"$\geq$",
           "µ": r"\textmu{}", "’": "'", "“": "``", "”": "''"}


def preprocess(md):
    md = re.sub(r"<style>.*?</style>\s*", "", md, flags=re.S)
    md = re.sub(r'<div class="cover-page".*?</div>\s*', "", md, flags=re.S)
    md = re.sub(r"## Table of contents.*?(?=## 1\.)", "", md, flags=re.S)
    # image + caption paragraph -> pandoc figure with that caption
    md = re.sub(r'!\[[^\]]*\]\(([^)]+)\)\s*\n\s*<p class="figure-caption">(.*?)</p>',
                lambda m: f"![{m.group(2)}]({m.group(1)}){{width=88%}}", md)
    md = re.sub(r"<sub>(.*?)</sub>", r"~\1~", md)
    return md


def main():
    FIGS.mkdir(exist_ok=True)
    for png in (ROOT / "figures").glob("*.png"):
        shutil.copy2(png, FIGS / png.name)
    md = preprocess((REP / "Report.md").read_text())
    body = subprocess.run(["pandoc", "-f", "markdown+pipe_tables+subscript", "-t", "latex", "--columns=60", "--no-highlight"],
                          input=md, capture_output=True, text=True, check=True).stdout
    for k, v in UNICODE.items():
        body = body.replace(k, v)
    body = re.sub(r"\\textasciitilde(\{\})?", lambda m: r"$\sim$", body)
    # same figure sizing as Project 3: full width, at most 42% of the page height, aspect ratio kept
    body = re.sub(r"\\includegraphics\[[^\]]*\]",
                  r"\\includegraphics[width=\\linewidth,height=0.42\\textheight,keepaspectratio]", body)
    (REP / "Report.tex").write_text(PREAMBLE + body + "\n\\end{document}\n")
    for _ in range(2):
        r = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "Report.tex"],
                           cwd=REP, capture_output=True, text=True)
        if r.returncode:
            print(r.stdout[-3000:])
            raise SystemExit("pdflatex failed")
    for ext in ("aux", "log", "out", "toc"):
        (REP / f"Report.{ext}").unlink(missing_ok=True)
    print("wrote", REP / "Report.tex", "and", REP / "Report.pdf")


if __name__ == "__main__":
    main()
