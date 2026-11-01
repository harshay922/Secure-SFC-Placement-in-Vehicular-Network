# =====================================================================
# step8_scaleout.py  -  STEP 8: partial scale-out to nearby RSUs
# ---------------------------------------------------------------------
# Run:  python step8_scaleout.py          (about 10 minutes: 4 runs of 1 hour, seed 1)
# Placement candidates of each VNF: entry RSU first -> (scale-out) un-flagged RSUs within 2 hops -> cloud.
# Compares, at 10% and 30% attackers:
#   D_detect_only = detection + exclusion, NO scale-out (a VNF that does not fit at the entry RSU goes to the cloud)
#   D_scaleout    = detection + exclusion + scale-out (only that VNF moves to a neighbour RSU within 2 hops)
# Outputs (in results/):
#   step8_compare_seed1.csv          - all numbers of the 4 runs
#   step8_window_latency.png         - average latency of SFCs arriving during the attack
#   step8_window_at_edge.png         - SFCs kept fully at the edge during the attack
# =====================================================================

import csv, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import config as cfg
from simulator import Simulation

SEED = cfg.SEEDS[0]
SHARES = [0.10, 0.30]
SCHEMES = ["D_detect_only", "D_scaleout"]
LABEL = {"D_detect_only": "detection + exclusion", "D_scaleout": "detection + exclusion + scale-out"}
runs = {}
for share in SHARES:
    for sch in SCHEMES:
        runs[(sch, share)] = Simulation(sch, SEED, attacker_share=share).run()

keys = ["window_latency_ms", "window_safety_latency_ms", "window_at_edge_pct", "window_safety_at_edge_pct",
        "vnfs_on_cloud_pct", "scaled_out_vnfs_pct", "window_disrupted_pct", "detection_rate_pct"]
cols = [(s, h) for h in SHARES for s in SCHEMES]
print("=" * 78); print("STEP 8 - partial scale-out (seed %d)" % SEED); print("=" * 78)
print(f"{'result':28s}" + "".join(f"{(('det ' if s == 'D_detect_only' else 'sco ') + str(int(h*100)) + '%'):>12s}" for s, h in cols))
for k in keys:
    print(f"{k:28s}" + "".join(f"{runs[c][k]:12.1f}" for c in cols))

p = os.path.join(cfg.RESULTS_DIR, f"step8_compare_seed{SEED}.csv")
with open(p, "w", newline="") as f:
    w = csv.writer(f); w.writerow(["result"] + [f"{s}_{int(h*100)}pct" for s, h in cols])
    for k in runs[cols[0]]: w.writerow([k] + [runs[c][k] for c in cols])
print(f"saved {p}")

for key, ylab, title, fname in [
        ("window_latency_ms", "average SFC latency (ms)", "Latency of SFCs arriving during the attack", "step8_window_latency.png"),
        ("window_at_edge_pct", "SFCs fully at the edge (%)", "SFCs kept at the edge during the attack", "step8_window_at_edge.png")]:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for sch in SCHEMES:
        ax.plot([h * 100 for h in SHARES], [runs[(sch, h)][key] for h in SHARES], marker="o", label=LABEL[sch])
    ax.set_xlabel("attacker cars (%)"); ax.set_ylabel(ylab); ax.set_title(title); ax.legend()
    p = os.path.join(cfg.RESULTS_DIR, fname)
    fig.savefig(p, dpi=150, bbox_inches="tight"); plt.close(fig); print(f"saved {p}")
print("\nRESULT: Step 8 OK")
