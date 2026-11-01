# =====================================================================
# step6_detection.py  -  STEP 6: adjusted-delta detection (ledger removed 25 Oct)
# ---------------------------------------------------------------------
# Run:  python step6_detection.py          (about 3 minutes, seed 1)
# Part B: 1 hour with 10% attackers, scheme "D_detect_only":
#         detection + exclusion of flagged RSUs from NEW placements (no migration yet).
# Outputs (in results/):
#   step6_summary_seed1.csv           - detection + service results
#   step6_flag_events_seed1.csv       - every flag: RSU, time, delta, phi, true/false alarm, un-flag time
#   step6_flagged_over_time.png       - flagged RSUs vs really attacked RSUs, every second
#   step6_attacked_rsu_flags.png      - most attacked RSU: hidden attack load + flagged periods
# =====================================================================

import csv, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import config as cfg
from simulator import Simulation
from detection import TRUE_ATTACK_SHARE

# ---------------- Part B: detection in the simulation ----------------
SEED = cfg.SEEDS[0]
sim = Simulation("D_detect_only", SEED, attacker_share=cfg.ATTACKER_SHARE)
res = sim.run()
print("\n" + "=" * 60); print("STEP 6B - detection + exclusion, 10%% attackers, seed %d" % SEED); print("=" * 60)
for k, v in res.items():
    print(f"{k:24s}: {v:.2f}" if isinstance(v, float) else f"{k:24s}: {v}")

p = os.path.join(cfg.RESULTS_DIR, f"step6_summary_seed{SEED}.csv")
with open(p, "w", newline="") as f:
    w = csv.writer(f); w.writerow(res.keys()); w.writerow(res.values())
print(f"saved {p}")
p = os.path.join(cfg.RESULTS_DIR, f"step6_flag_events_seed{SEED}.csv")
with open(p, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["rsu", "flag_s", "delta", "phi", "true_attack", "unflag_s"])
    w.writeheader(); w.writerows(sim.det.events)
print(f"saved {p}")

rsus = list(sim.net.rsus)
hidden = np.array([row[1:] for row in sim.att_timeline])                 # attack share, seconds x RSUs
times = [row[0] for row in sim.att_timeline]
fig, ax = plt.subplots(figsize=(8, 4.5))
ax.plot(times, (hidden > TRUE_ATTACK_SHARE).sum(axis=1), label="really attacked RSUs (attack load > 10%)")
ax.plot([t for t, _ in sim.det.flag_timeline], [n for _, n in sim.det.flag_timeline], label="flagged RSUs")
ax.axvspan(cfg.ATTACK_START_S, cfg.ATTACK_END_S, color="red", alpha=0.08, label="attack window")
ax.set_xlabel("simulation time (s)"); ax.set_ylabel("number of RSUs")
ax.set_title("Detection: flagged RSUs vs really attacked RSUs"); ax.legend()
p = os.path.join(cfg.RESULTS_DIR, "step6_flagged_over_time.png")
fig.savefig(p, dpi=150, bbox_inches="tight"); plt.close(fig); print(f"saved {p}")

top = rsus[int(hidden.mean(axis=0).argmax())]                            # most attacked RSU
fig, ax = plt.subplots(figsize=(8, 4.5))
ax.plot(times, hidden[:, rsus.index(top)] * 100, label="hidden attack load")
first = True
for e in sim.det.events:                                                 # shade every flagged period of this RSU
    if e["rsu"] == top:
        end = e["unflag_s"] if e["unflag_s"] != "" else cfg.SIM_DURATION_S
        ax.axvspan(e["flag_s"], end, color="grey", alpha=0.3, label="flagged" if first else None); first = False
ax.set_xlabel("simulation time (s)"); ax.set_ylabel("attack CPU load (% of RSU capacity)")
ax.set_title(f"Most attacked RSU ({top}): attack load and flagged periods"); ax.legend()
p = os.path.join(cfg.RESULTS_DIR, "step6_attacked_rsu_flags.png")
fig.savefig(p, dpi=150, bbox_inches="tight"); plt.close(fig); print(f"saved {p}")
print("\nRESULT: Step 6 OK")
