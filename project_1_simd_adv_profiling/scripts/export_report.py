"""Export report/Report.md to LaTeX; optionally compile with a local TeX engine.

Usage: python scripts/export_report.py [--engine pdflatex|xelatex|tectonic]
Report.md is the hand-written source of truth. analysis/analyze.py does not
modify it; it writes regenerated tables to results/processed/generated_tables.md instead.
"""
import argparse
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]

UNICODE = {
    '×': r'$\times$', 'µ': r'\textmu{}', '–': '--', '—': '---', '−': r'$-$',
    '≈': r'$\approx$', '→': r'$\rightarrow$', '≠': r'$\neq$', '·': r'$\cdot$',
    '≤': r'$\leq$', '≥': r'$\geq$', '’': "'", '‘': '`', '“': '``', '”': "''",
}


def escape(text):
    subs = {'\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$',
            '#': r'\#', '_': r'\_', '{': r'\{', '}': r'\}',
            '~': r'\textasciitilde{}', '^': r'\textasciicircum{}'}
    out = ''.join(subs.get(c, c) for c in text)
    for k, v in UNICODE.items():
        out = out.replace(k, v)
    return out


def emphasis(text):
    """Escape plain text and convert **bold** and *italic*."""
    parts = re.split(r'(\*\*[^*]+\*\*|\*[^*\s][^*]*\*)', text.replace(r'\*', '\x00'))
    out = []
    for p in parts:
        if p.startswith('**') and p.endswith('**') and len(p) > 4:
            out.append(r'\textbf{' + escape(p[2:-2]) + '}')
        elif p.startswith('*') and p.endswith('*') and len(p) > 2:
            out.append(r'\textit{' + escape(p[1:-1]) + '}')
        else:
            out.append(escape(p))
    return ''.join(out).replace('\x00', '*')


def inline(text):
    pattern = r'`([^`]+)`|\[([^\]]+)\]\(([^)]+)\)|(https?://\S+)'
    result, start = [], 0
    for m in re.finditer(pattern, text):
        result.append(emphasis(text[start:m.start()]))
        code, label, url, bare = m.groups()
        if code is not None:
            result.append(r'\texttt{' + escape(code) + '}')
        elif label is not None:
            if url.startswith(('https://', 'http://')):
                result.append(r'\href{' + url.replace('%', r'\%').replace('#', r'\#') + '}{' + emphasis(label) + '}')
            else:
                result.append(emphasis(label))
        else:
            result.append(r'\url{' + bare + '}')
        start = m.end()
    result.append(emphasis(text[start:]))
    return ''.join(result)


def table(rows):
    n = len(rows[0])
    lengths = [max(min(len(r[j]), 60) for r in rows) + 4 for j in range(n)]
    total = sum(lengths)
    spec = ''.join(r'>{\raggedright\arraybackslash}p{' + f'{l/total:.4f}' +
                   r'\dimexpr\linewidth-' + str(2*n) + r'\tabcolsep\relax}' for l in lengths)
    out = [r'\Needspace{' + str(min(len(rows)+3, 14)) + r'\baselineskip}',
           r'{\footnotesize\begin{longtable}{' + spec + r'}\toprule',
           ' & '.join(r'\textbf{' + inline(c) + '}' for c in rows[0]) + r' \\ \midrule\endhead']
    out += [' & '.join(inline(c) for c in row) + r' \\' for row in rows[1:]]
    out.append(r'\bottomrule\end{longtable}}')
    return '\n'.join(out)


def heading(text, level):
    cmd = {2: 'section', 3: 'subsection'}[level]
    need = 12 if level == 2 else 8
    if text.startswith('Appendix'):
        need = 40  # start the appendix on a fresh page
    return (r'\Needspace{' + str(need) + r'\baselineskip}' + '\n' +
            '\\' + cmd + '*{' + inline(text) + '}\n' +
            r'\addcontentsline{toc}{' + cmd + '}{' + inline(text) + '}')


def export():
    lines = (ROOT / 'report/Report.md').read_text(encoding='utf-8').splitlines()
    body, i, skip_toc = [], 0, False
    while i < len(lines):
        raw = lines[i]
        line = raw.strip()
        # HTML-only blocks used for the Markdown/print rendering.
        if line.startswith('<style'):
            while not lines[i].strip().startswith('</style>'):
                i += 1
            i += 1
            continue
        if line.startswith('<div class="cover-page"'):
            while not lines[i].strip().startswith('</div>'):
                i += 1
            i += 1
            continue
        if line.startswith('<p ') and 'figure-caption' in line:
            i += 1
            continue
        if line.startswith('## '):
            skip_toc = line[3:].strip().lower() == 'table of contents'
            if not skip_toc:
                body.append(heading(line[3:], 2))
            i += 1
            continue
        if skip_toc or not line or line.startswith('# '):
            i += 1
            continue
        if line.startswith('### '):
            body.append(heading(line[4:], 3))
        elif line.startswith('```'):
            code = []
            i += 1
            while not lines[i].strip().startswith('```'):
                code.append(lines[i])
                i += 1
            body.append(r'{\footnotesize\begin{verbatim}' + '\n' + '\n'.join(code) + '\n' + r'\end{verbatim}}')
        elif line.startswith('|'):
            rows = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                cells = [c.strip() for c in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?', c) for c in cells):
                    rows.append(cells)
                i += 1
            body.append(table(rows))
            continue
        elif line.startswith('!['):
            caption, path = re.fullmatch(r'!\[([^\]]*)\]\(([^)]+)\)', line).groups()
            caption = re.sub(r'^Figure \d+\.\s*', '', caption)
            body.append(r'\par\noindent\begin{minipage}{\linewidth}\centering\includegraphics[width=0.92\linewidth,height=0.42\textheight,keepaspectratio]{' +
                        path + r'}\captionof{figure}{' + inline(caption) + r'}\end{minipage}\par\medskip')
        elif line.startswith('- '):
            body.append(r'\begin{itemize}\setlength{\itemsep}{2pt}')
            while i < len(lines) and lines[i].strip().startswith('- '):
                body.append(r'\item ' + inline(lines[i].strip()[2:]))
                i += 1
            body.append(r'\end{itemize}')
            continue
        elif re.match(r'\d+\. ', line):
            body.append(r'\begin{enumerate}\setlength{\itemsep}{2pt}')
            while i < len(lines) and re.match(r'\d+\. ', lines[i].strip()):
                body.append(r'\item ' + inline(re.sub(r'^\d+\.\s+', '', lines[i].strip())))
                i += 1
            body.append(r'\end{enumerate}')
            continue
        elif line.startswith('*') and line.endswith('*') and not line.startswith('**'):
            body.append(r'\vspace{-4pt}{\centering\footnotesize\textit{' + inline(line[1:-1]) + r'}\par}')
        else:
            paragraph = [line]
            while i + 1 < len(lines) and lines[i+1].strip() and not lines[i+1].lstrip().startswith(('#', '|', '![', '- ', '<', '```')):
                i += 1
                paragraph.append(lines[i].strip())
            body.append(inline(' '.join(paragraph)) + '\n')
        i += 1

    preamble = r'''\documentclass[10pt,letterpaper]{article}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{textcomp}
\IfFileExists{lmodern.sty}{\usepackage{lmodern}}{}
\usepackage[margin=0.7in]{geometry}
\usepackage{graphicx,longtable,booktabs,array}
\usepackage[hidelinks]{hyperref}
\usepackage{microtype,needspace,caption,placeins}
\captionsetup{justification=centering,singlelinecheck=false,font=small,labelfont=it,textfont=it}
\setlength{\LTpre}{4pt}
\setlength{\LTpost}{6pt}
\setcounter{tocdepth}{2}
\setlength{\parindent}{0pt}
\setlength{\parskip}{6pt}
\setlength{\tabcolsep}{3pt}
\renewcommand{\arraystretch}{1.18}
\renewcommand{\contentsname}{Table of contents}
\emergencystretch=3em
\widowpenalty=10000
\clubpenalty=10000
\hypersetup{pdftitle={Project 1: SIMD Advantage Profiling},pdfauthor={Rashid Shabab}}
\begin{document}
\begin{titlepage}
\thispagestyle{empty}\centering
\vspace*{1.2in}
{\Large\bfseries ECSE 6320\par}
\vspace{0.3in}
{\Large Advanced Computer Systems\par}
\vspace{0.9in}
{\LARGE\bfseries Project 1: SIMD Advantage Profiling\par}
\vspace{0.9in}
{\large Submitted by Rashid Shabab\par}
\vfill
\end{titlepage}
\setcounter{page}{2}
{\setlength{\parskip}{0pt}\tableofcontents}\clearpage
'''
    output = ROOT / 'report/Report.tex'
    output.write_text(preamble + '\n\n'.join(body) + '\n\\end{document}\n', encoding='utf-8')
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', help='tectonic, pdflatex or xelatex (name or path)')
    args = parser.parse_args()
    source = export()
    print(f'Exported {source}')
    if args.engine:
        engine = str(Path(args.engine).resolve()) if Path(args.engine).exists() else args.engine
        if 'tectonic' in Path(engine).name.lower():
            subprocess.run([engine, source.name], cwd=source.parent, check=True)
        else:
            for _ in range(2):  # second pass fills the table of contents
                subprocess.run([engine, '-interaction=nonstopmode', '-halt-on-error', source.name],
                               cwd=source.parent, check=True, stdout=subprocess.DEVNULL)
            for ext in ('aux', 'log', 'out', 'toc'):
                try:
                    (source.parent / f'Report.{ext}').unlink(missing_ok=True)
                except OSError:
                    pass
        print(f'Compiled {source.with_suffix(".pdf")}')


if __name__ == '__main__':
    main()
