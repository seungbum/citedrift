"""Submission gate for paper/: no \\pending markers, no undefined citations/references, at most 4 pages.

Usage: .venv/bin/python -I src/check_paper.py <paper_dir>
"""
import glob, os, re, subprocess, sys


def main():
    d = sys.argv[1]
    problems = []
    for f in [os.path.join(d, "main.tex"), os.path.join(d, "numbers.tex")] + glob.glob(os.path.join(d, "sections", "*.tex")):
        for i, line in enumerate(open(f), 1):
            if "\\pending{" in line and "\\newcommand{\\pending}" not in line and not line.lstrip().startswith("%"):
                problems.append(f"{os.path.relpath(f, d)}:{i}: pending: {line.strip()[:100]}")
    log = os.path.join(d, "build.log")
    if os.path.exists(log):
        t = open(log, errors="replace").read()
        for m in re.findall(r"(Citation `[^']+' on page \d+ undefined|Reference `[^']+' on page \d+ undefined)", t):
            problems.append("latex: " + m)
    pdf = os.path.join(d, "main.pdf")
    if os.path.exists(pdf):
        info = subprocess.run(["pdfinfo", pdf], capture_output=True, text=True).stdout
        pages = int(re.search(r"Pages:\s+(\d+)", info).group(1))
        if pages > 4:
            problems.append(f"pdf has {pages} pages (limit 4 including references)")
    else:
        problems.append("main.pdf missing")
    for p in problems:
        print(p)
    print(f"{len(problems)} problem(s)")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
