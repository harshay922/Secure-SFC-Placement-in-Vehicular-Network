# =====================================================================
# step5_attack.py  -  STEP 5: DDoS attack, NO defence (scheme S0)
# ---------------------------------------------------------------------
# Run:  python step5_attack.py          (about 4 minutes: 2 runs of 1 hour, seed 1)
# Run 1: no attackers (same as Step 4).   Run 2: 10% attacker cars, attacking only from t = 1200 s to 2400 s.
# Outputs (in results/):
#   step5_compare_seed1.csv              - no attack vs attack, all main numbers
#   step5_attacked_rsu_load.png          - most attacked RSU: known load vs hidden attack load
#   step5_latency_over_time.png          - average latency of running SFCs, no attack vs attack
#   step5_disrupted_over_time.png        - SFCs whose service is stopped, every second
#   step5_attack_load_per_rsu.png        - average hidden attack CPU load on each RSU
# =====================================================================

import csv, os                                  # csv writing, paths
import numpy as np                              # arrays
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import config as cfg
from simulator import Simulation

SEED = cfg.SEEDS[0]                                             # seed 1
clean = Simulation("S0_no_defense", SEED, attacker_share=0.0)   # run 1: no attack
r0 = clean.run()
att = Simulation("S0_no_defense", SEED, attacker_share=cfg.ATTACKER_SHARE)   # run 2: 10% attackers
r1 = att.run()

print("=" * 66)
print("STEP 5 - attack without defence (S0), seed %d" % SEED)
print("=" * 66)
print(f"{'result':24s} {'no attack':>14s} {'10% attackers':>16s}")
for k in r0:                                                    # print both runs side by side
    a, b = r0[k], r1[k]
    fa = f"{a:14.2f}" if isinstance(a, float) else f"{str(a):>14s}"
    fb = f"{b:16.2f}" if isinstance(b, float) else f"{str(b):>16s}"
    print(f"{k:24s} {fa} {fb}")
n_att = sum(att.is_attacker.values())
print(f"\nattacker cars: {n_att} of {len(att.is_attacker)} ({n_att/len(att.is_attacker)*100:.1f}%)")

p = os.path.join(cfg.RESULTS_DIR, f"step5_compare_seed{SEED}.csv")
with open(p, "w", newline="") as f:
    w = csv.writer(f); w.writerow(["result", "no_attack", "attack_10pct"])
    for k in r0: w.writerow([k, r0[k], r1[k]])
print(f"saved {p}")

rsus = list(att.net.rsus)
known = np.array([row[1:] for row in att.util_timeline]) * 100     # % of capacity, seconds x RSUs
hidden = np.array([row[1:] for row in att.att_timeline]) * 100
times = [row[0] for row in att.util_timeline]
top = rsus[int(hidden.mean(axis=0).argmax())]                     # RSU with the most attack load
i = rsus.index(top)

fig, ax = plt.subplots(figsize=(8, 4.5))
ax.plot(times, known[:, i], label="known load (VNFs placed by orchestrator)")
ax.plot(times, hidden[:, i], label="hidden attack load")
ax.plot(times, known[:, i] + hidden[:, i], label="total CPU demand")
ax.axhline(100, color="black", linestyle="--", label="RSU capacity (96 cores)")
ax.set_xlabel("simulation time (s)"); ax.set_ylabel("CPU demand (% of RSU capacity)")
ax.axvspan(cfg.ATTACK_START_S, cfg.ATTACK_END_S, color="red", alpha=0.08, label="attack window")
ax.set_title(f"Most attacked RSU ({top}), no defence"); ax.legend()
p = os.path.join(cfg.RESULTS_DIR, "step5_attacked_rsu_load.png")
fig.savefig(p, dpi=150, bbox_inches="tight"); plt.close(fig); print(f"saved {p}")

fig, ax = plt.subplots(figsize=(8, 4.5))
ax.plot([x[0] for x in clean.lat_timeline], [x[1] for x in clean.lat_timeline], label="no attack")
ax.plot([x[0] for x in att.lat_timeline], [x[1] for x in att.lat_timeline], label="10% attackers, no defence")
ax.set_xlabel("simulation time (s)"); ax.set_ylabel("average latency of working SFCs (ms)")
ax.axvspan(cfg.ATTACK_START_S, cfg.ATTACK_END_S, color="red", alpha=0.08, label="attack window")
ax.set_title("Latency of running SFCs"); ax.legend()
p = os.path.join(cfg.RESULTS_DIR, "step5_latency_over_time.png")
fig.savefig(p, dpi=150, bbox_inches="tight"); plt.close(fig); print(f"saved {p}")

fig, ax = plt.subplots(figsize=(8, 4.5))
ax.plot([x[0] for x in clean.lat_timeline], [x[2] for x in clean.lat_timeline], label="no attack")
ax.plot([x[0] for x in att.lat_timeline], [x[2] for x in att.lat_timeline], label="10% attackers, no defence")
ax.set_xlabel("simulation time (s)"); ax.set_ylabel("disrupted SFCs (SFCs)")
ax.axvspan(cfg.ATTACK_START_S, cfg.ATTACK_END_S, color="red", alpha=0.08, label="attack window")
ax.set_title("SFCs whose service is stopped by CPU starvation"); ax.legend()
p = os.path.join(cfg.RESULTS_DIR, "step5_disrupted_over_time.png")
fig.savefig(p, dpi=150, bbox_inches="tight"); plt.close(fig); print(f"saved {p}")

ids = sorted(rsus, key=lambda r: int(r.replace("RSU", "")))
fig, ax = plt.subplots(figsize=(8, 4.5))
ax.plot(range(len(ids)), [hidden[:, rsus.index(r)].mean() for r in ids], marker="o")
ax.set_xticks(range(len(ids))); ax.set_xticklabels([r.replace("RSU", "") for r in ids])
ax.set_xlabel("RSU number"); ax.set_ylabel("average attack CPU load (% of capacity)")
ax.set_title("Hidden attack load on each RSU (10% attackers)")
p = os.path.join(cfg.RESULTS_DIR, "step5_attack_load_per_rsu.png")
fig.savefig(p, dpi=150, bbox_inches="tight"); plt.close(fig); print(f"saved {p}")
print("\nRESULT: Step 5 OK")
