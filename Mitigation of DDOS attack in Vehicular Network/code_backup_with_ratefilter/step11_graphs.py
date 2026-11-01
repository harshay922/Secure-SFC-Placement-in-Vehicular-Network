# =====================================================================
# step11_graphs.py  -  STEP 11: final graphs + summary tables, per attack scenario
# ---------------------------------------------------------------------
# Run:  python step11_graphs.py          (a few seconds; needs Step 10's csv)
# Every graph: plain line graph, x = attacker cars (%), one line per scheme,
# value = mean over the seeds, error bar = standard deviation over the seeds.
# The no-attack runs (scenario "none", 0 %) are the first point of every scenario.
# Outputs (in results/final/ or results/quick/):
#   <scenario>/g01_*.png ... g08_*.png       - one graph per metric
#   <scenario>/g09_latency_over_time_10pct.png
#   <scenario>/summary_table.csv              - mean and std of every metric
#   compare_scenarios_latency_reduction.png   - how much S3 lowers latency vs S0, per scenario
# =====================================================================

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import config as cfg

BASE = os.path.join(cfg.RESULTS_DIR, "quick" if cfg.QUICK_MODE else "final")
os.makedirs(BASE, exist_ok=True)
df = pd.read_csv(os.path.join(cfg.RESULTS_DIR, "step10_quick_runs.csv" if cfg.QUICK_MODE else "step10_all_runs.csv"))
df["share_pct"] = (df["attacker_share"] * 100).round().astype(int)   # 0.1 -> 10
NAMES = {"S0_no_defense": "S0 no defence",
         "S1_detect_only": "S1 detection + exclusion only",
         "S2_detect_scaleout": "S2 detection + scale-out (no migration)",
         "S3_proposed": "S3 proposed (all layers + rate filter)"}
GRAPHS = [
    ("window_failed_pct", "failed SFCs (%)", "SFCs that failed (dropped, stopped or > 100 ms) during the attack"),
    ("window_running_latency_ms", "average latency of running SFCs (ms)", "Latency during the attack window (all running SFCs)"),
    ("window_latency_ms", "average latency of new SFCs (ms)", "Latency of SFCs that arrived during the attack"),
    ("window_at_edge_pct", "SFCs fully at the edge (%)", "SFCs kept at the edge during the attack"),
    ("vnfs_on_cloud_pct", "VNFs placed on the cloud (%)", "Share of VNFs sent to the cloud (whole hour)"),
    ("window_disrupted_sfc_s", "disrupted SFC-seconds (SFC x s)", "Service stopped by CPU starvation during the attack"),
    ("detection_rate_pct", "attack episodes detected (%)", "Detection rate"),
    ("false_alarms_per_h", "false alarms (per hour)", "False alarms of the detector"),
    ("migrations", "migrated VNFs (VNFs)", "VNFs migrated off flagged RSUs"),
]
metrics = [c for c in df.columns if df[c].dtype != object and c not in ("seed", "attacker_share", "share_pct")]
none = df[df.scenario == "none"]                                      # no-attack reference rows
reduction = {}                                                        # scenario -> {share: % latency reduction of S3}

SWEEP_SCENARIOS = [sc for sc in cfg.ATTACK_SCENARIOS if sc != "D_jam"]   # scenarios with an attacker-share sweep
for sc in SWEEP_SCENARIOS:
    out = os.path.join(BASE, sc); os.makedirs(out, exist_ok=True)
    d = pd.concat([none, df[df.scenario == sc]])                      # 0 % point + this scenario
    g = d.groupby(["scheme", "share_pct"])[metrics]
    table = g.mean(numeric_only=True).round(3).add_suffix("_mean").join(g.std(numeric_only=True).round(3).add_suffix("_std"))
    table.to_csv(os.path.join(out, "summary_table.csv"))
    for k, (col, ylab, title) in enumerate(GRAPHS, 1):
        fig, ax = plt.subplots(figsize=(8, 4.5))
        for sch, name in NAMES.items():
            x = d[d.scheme == sch]
            if x[col].isna().all():
                continue
            m = x.groupby("share_pct")[col].mean(); s = x.groupby("share_pct")[col].std()
            ax.errorbar(m.index, m.values, yerr=s.values, marker="o", capsize=3, label=name)
        ax.set_xlabel("attacker cars (%)"); ax.set_ylabel(ylab); ax.set_title(f"{title} - scenario {sc}"); ax.legend()
        fig.savefig(os.path.join(out, f"g{k:02d}_{col}.png"), dpi=150, bbox_inches="tight"); plt.close(fig)
    fig, ax = plt.subplots(figsize=(8, 4.5))                          # latency over time, seed 1, 10 %
    for sch, name in NAMES.items():
        p = os.path.join(cfg.RESULTS_DIR, f"step10_timeline_{sc}_{sch}_10pct.csv")
        if os.path.isfile(p):
            t = pd.read_csv(p)
            ax.plot(t.time_s, t.avg_latency_running_ms.rolling(30, min_periods=1).mean(), label=name)
    ax.axvspan(cfg.ATTACK_START_S, cfg.ATTACK_END_S, color="red", alpha=0.08, label="attack window")
    ax.set_xlabel("simulation time (s)"); ax.set_ylabel("average latency of running SFCs (ms)")
    ax.set_title(f"Latency over time, 10% attackers, seed 1 - scenario {sc}"); ax.legend()
    fig.savefig(os.path.join(out, "g09_latency_over_time_10pct.png"), dpi=150, bbox_inches="tight"); plt.close(fig)
    lat = d.groupby(["scheme", "share_pct"])["window_running_latency_ms"].mean()
    reduction[sc] = {sh: (lat["S0_no_defense"][sh] - lat["S3_proposed"][sh]) / lat["S0_no_defense"][sh] * 100
                     for sh in sorted(d.share_pct.unique()) if sh > 0}
    print(f"saved graphs for scenario {sc} in {out}")

# ---------------- scenario D (jam zone): no sweep -> table + latency over time ----------------
if "D_jam" in cfg.ATTACK_SCENARIOS and (df.scenario == "D_jam").any():
    out = os.path.join(BASE, "D_jam"); os.makedirs(out, exist_ok=True)
    dj = df[df.scenario == "D_jam"]
    cols = ["win_active_sfcs", "win_hit_sfcs", "win_failed_sfcs", "win_cloud_sfcs", "win_edge_sfcs", "win_migrated_sfcs", "window_failed_pct", "window_dropped_pct", "window_running_latency_ms", "window_latency_ms", "window_at_edge_pct", "vnfs_on_cloud_pct",
            "window_disrupted_sfc_s", "detection_rate_pct", "detection_delay_s", "migrations", "migrations_to_cloud"]
    tab = dj.groupby("scheme")[cols].agg(["mean", "std"]).round(2)
    tab.to_csv(os.path.join(out, "summary_table.csv"))
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for sch, name in NAMES.items():
        p = os.path.join(cfg.RESULTS_DIR, f"step10_timeline_D_jam_{sch}_10pct.csv")
        if os.path.isfile(p):
            t = pd.read_csv(p)
            ax.plot(t.time_s, t.avg_latency_running_ms.rolling(30, min_periods=1).mean(), label=name)
    ax.axvspan(cfg.ATTACK_START_S, cfg.ATTACK_END_S, color="red", alpha=0.08, label="attack window")
    ax.set_xlabel("simulation time (s)"); ax.set_ylabel("average latency of running SFCs (ms)")
    ax.set_title("Latency over time, seed 1 - scenario D_jam (jam zone around RSU3)"); ax.legend()
    fig.savefig(os.path.join(out, "g09_latency_over_time.png"), dpi=150, bbox_inches="tight"); plt.close(fig)
    print("\nscenario D_jam (mean over seeds):"); print(dj.groupby("scheme")[cols].mean().round(1).T.to_string())

fig, ax = plt.subplots(figsize=(8, 4.5))                              # S3 benefit per scenario
for sc, red in reduction.items():
    ax.plot(list(red.keys()), list(red.values()), marker="o", label=f"scenario {sc}")
ax.set_xlabel("attacker cars (%)"); ax.set_ylabel("latency reduction of S3 vs S0 (%)")
ax.set_title("How much the proposed defence lowers attack-time latency"); ax.legend()
p = os.path.join(BASE, "compare_scenarios_latency_reduction.png")
fig.savefig(p, dpi=150, bbox_inches="tight"); plt.close(fig); print(f"saved {p}")

show = ["win_active_sfcs", "win_hit_sfcs", "win_failed_sfcs", "win_cloud_sfcs", "win_edge_sfcs", "win_migrated_sfcs", "window_failed_pct", "window_dropped_pct", "window_running_latency_ms", "window_at_edge_pct", "vnfs_on_cloud_pct", "detection_rate_pct",
        "detection_delay_s", "false_alarms_per_h", "migrations"]
for sc in SWEEP_SCENARIOS:
    print(f"\nscenario {sc}, 10% attackers (mean over seeds):")
    print(df[(df.scenario == sc) & (df.share_pct == 10)].groupby("scheme")[show].mean().round(1).T.to_string())
print("\nno attack (mean over seeds):")
print(none.groupby("scheme")[["window_failed_pct", "window_running_latency_ms", "vnfs_on_cloud_pct"]].mean().round(1).T.to_string())
print("\nRESULT: Step 11 OK")
