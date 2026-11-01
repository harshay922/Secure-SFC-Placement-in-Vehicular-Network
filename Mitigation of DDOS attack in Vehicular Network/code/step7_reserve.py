# =====================================================================
# step7_reserve.py  -  STEP 7: criticality reserve for safety SFCs
# ---------------------------------------------------------------------
# Run:  python step7_reserve.py           (about 10 minutes: 4 runs of 1 hour, seed 1)
# Compares, at 10% and 30% attackers:
#   D_detect_only   = detection + exclusion (Step 6)
#   OLD_criticality = detection + exclusion + 30% safety reserve on RSUs within 2 hops of a flagged RSU
# Outputs (in results/):
#   step7_compare_seed1.csv              - all numbers of the 4 runs
#   step7_safety_at_edge.png             - safety SFCs kept fully at the edge during the attack
#   step7_reserve_rsus_over_time.png     - how many RSUs have an active reserve (30% attackers)
# =====================================================================

import csv, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import config as cfg
from simulator import Simulation

SEED = cfg.SEEDS[0]
SHARES = [0.10, 0.30]                                       # two attack strengths
SCHEMES = ["D_detect_only", "OLD_criticality"]              # without / with reserve
runs = {}                                                   # (scheme, share) -> (summary, simulation)
for share in SHARES:
    for sch in SCHEMES:
        sim = Simulation(sch, SEED, attacker_share=share)
        runs[(sch, share)] = (sim.run(), sim)

keys = ["window_latency_ms", "window_safety_latency_ms", "window_safety_at_edge_pct", "nonsafety_at_edge_pct",
        "vnfs_on_cloud_pct", "window_disrupted_pct", "reserve_skips", "att_fake_into_reserve",
        "avg_reserve_rsus_in_window", "detection_rate_pct", "avg_flagged_in_window"]
print("=" * 78); print("STEP 7 - criticality reserve (seed %d)" % SEED); print("=" * 78)
cols = [(sch, sh) for sh in SHARES for sch in SCHEMES]
print(f"{'result':28s}" + "".join(f"{(('det ' if s == 'D_detect_only' else 'res ') + str(int(h*100)) + '%'):>12s}" for s, h in cols))
for k in keys:
    print(f"{k:28s}" + "".join(f"{runs[c][0][k]:12.1f}" for c in cols))

p = os.path.join(cfg.RESULTS_DIR, f"step7_compare_seed{SEED}.csv")
with open(p, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["result"] + [f"{s}_{int(h*100)}pct" for s, h in cols])
    for k in runs[cols[0]][0]:
        w.writerow([k] + [runs[c][0][k] for c in cols])
print(f"saved {p}")

fig, ax = plt.subplots(figsize=(8, 4.5))
for sch, lab in [("D_detect_only", "detection + exclusion"), ("OLD_criticality", "detection + exclusion + safety reserve")]:
    ax.plot([h * 100 for h in SHARES], [runs[(sch, h)][0]["window_safety_at_edge_pct"] for h in SHARES], marker="o", label=lab)
ax.set_xlabel("attacker cars (%)"); ax.set_ylabel("safety SFCs fully at the edge (%)")
ax.set_title("Safety SFCs kept at the edge during the attack window"); ax.legend()
p = os.path.join(cfg.RESULTS_DIR, "step7_safety_at_edge.png")
fig.savefig(p, dpi=150, bbox_inches="tight"); plt.close(fig); print(f"saved {p}")

sim = runs[("OLD_criticality", 0.30)][1]
fig, ax = plt.subplots(figsize=(8, 4.5))
ax.plot([t for t, _ in sim.reserve_timeline], [z for _, z in sim.reserve_timeline])
ax.axvspan(cfg.ATTACK_START_S, cfg.ATTACK_END_S, color="red", alpha=0.08, label="attack window")
ax.set_xlabel("simulation time (s)"); ax.set_ylabel("RSUs with an active reserve (RSUs)")
ax.set_title("Active safety reserves over time (30% attackers)"); ax.legend()
p = os.path.join(cfg.RESULTS_DIR, "step7_reserve_rsus_over_time.png")
fig.savefig(p, dpi=150, bbox_inches="tight"); plt.close(fig); print(f"saved {p}")
print("\nRESULT: Step 7 OK")
