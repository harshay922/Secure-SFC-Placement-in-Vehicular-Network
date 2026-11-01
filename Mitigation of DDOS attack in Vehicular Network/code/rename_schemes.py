# rename_schemes.py - renames the schemes everywhere:  S0 -> S0,  S1a -> S1,  S1b -> S2,  S1 (proposed) -> S3
# Usage: python rename_schemes.py "<path of the MTP DDOS attack folder>"
import os, sys, re
root = sys.argv[1]
TOK = [("S1_proposed", "@@S3P@@"), ("S1a_detect_only", "S1_detect_only"), ("S1b_detect_scaleout", "S2_detect_scaleout"),
       ("S1a_criticality", "OLD_criticality"), ("@@S3P@@", "S3_proposed")]          # placeholder avoids S1 -> S3 clash
CODE = {   # exact text in comments / labels (file -> list of (old, new))
 "code/config.py": [("S1 rate filter at EVERY RSU", "S3 rate filter at EVERY RSU"), ("part of migration (S1)", "part of migration (S3)"),
                    ("(same as S1a)", "(same as S1)"), ("(same as S1b)", "(same as S2)")],
 "code/simulator.py": [("# S1: rate filter", "# S3: rate filter"), ("With the S1 rate filter", "With the S3 rate filter"),
                       ("reserve rules still apply (S1)", "reserve rules still apply (S3)"), ("# S1: cars leave", "# S3: cars leave"),
                       ("# S1: re-associate", "# S3: re-associate"), ("# S1: entry moved", "# S3: entry moved")],
 "code/step11_graphs.py": [("S1 proposed (all layers + rate filter)", "S3 proposed (all layers + rate filter)"),
                           ("S1a detection + exclusion only", "S1 detection + exclusion only"),
                           ("S1b detection + scale-out (no migration)", "S2 detection + scale-out (no migration)"),
                           ("how much S1 lowers latency", "how much S3 lowers latency"), ("% latency reduction of S1}", "% latency reduction of S3}"),
                           ("# S1 benefit per scenario", "# S3 benefit per scenario"), ("latency reduction of S1 vs S0 (%)", "latency reduction of S3 vs S0 (%)")],
}
def tok(s):
    for a, b in TOK: s = s.replace(a, b)
    return s
n_files = 0
# 1) code: exact comment/label edits first, then the scheme names
for rel in ["code/config.py", "code/simulator.py", "code/step10_experiments.py", "code/step11_graphs.py", "code/step7_reserve.py", "code/detection.py"]:
    p = os.path.join(root, rel)
    if not os.path.isfile(p): continue
    s0 = s = open(p, encoding="utf-8").read()
    for a, b in CODE.get(rel, []):
        if a not in s: print("  note: not found in", rel, ":", a)
        s = s.replace(a, b)
    s = tok(s)
    if s != s0: open(p, "w", encoding="utf-8").write(s); n_files += 1; print("code  ", rel)
# 2) every csv under results/: scheme names inside the file + file names
for d, _, fs in os.walk(os.path.join(root, "results")):
    for f in fs:
        p = os.path.join(d, f)
        if f.endswith(".csv"):
            s0 = open(p, encoding="utf-8").read(); s = tok(s0)
            if s != s0: open(p, "w", encoding="utf-8").write(s); n_files += 1
        nf = tok(f)
        if nf != f: os.rename(p, os.path.join(d, nf)); print("rename", os.path.relpath(os.path.join(d, nf), root))
print("done, files changed:", n_files)
