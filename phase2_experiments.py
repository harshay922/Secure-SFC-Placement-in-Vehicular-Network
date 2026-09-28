"""PHASE 2 - STEP 5: experiments and graphs.

Scenario: 20 RSUs (SPAVM scenario 2), 80 vehicles, 50 slots, 5 seeds.
Attacks: the five VeReMi position-falsification types.
Writes CSV tables + PNG graphs to results/phase2/.
Run:  python phase2_experiments.py        (about 5-8 minutes)
"""
import csv
import os
import statistics
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import config
from spavm.simulator import Simulator

OUT = "results/phase2"
SEEDS = [1, 2, 3, 4, 5]
N_RSU, N_SLOTS, N_VEH = 20, 50, 80
FRACS = [0.0, 0.1, 0.2, 0.3, 0.4]
SCHEMES = {                                   # name -> (mobility_mode, storm_guard)
    "SPAVM": ("none", False),
    "Ignore reports": ("ignore", False),
    "Confidence (ours)": ("conf", False),
    "Confidence + guard (ours)": ("conf", True),
    "Oracle": ("oracle", False),
}
COLOR = {"SPAVM": "#eb6834", "Ignore reports": "#eda100", "Confidence (ours)": "#2a78d6",
         "Confidence + guard (ours)": "#e87ba4", "Oracle": "#1baf7a"}
MARK = {"SPAVM": "o", "Ignore reports": "D", "Confidence (ours)": "s",
        "Confidence + guard (ours)": "P", "Oracle": "^"}
DASH = {k: ("--" if k == "Oracle" else "-") for k in SCHEMES}

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "axes.edgecolor": GRID,
                     "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "text.color": INK,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "font.size": 10,
                     "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False})


def sim(mode, guard, frac, lmode, seed):
    return Simulator(N_RSU, N_SLOTS, N_VEH, seed=seed, phase2=True, mobility_mode=mode,
                     liar_fraction=frac, liar_mode=lmode, storm_guard=guard)


def avg(mode, guard, frac, lmode):
    runs = [sim(mode, guard, frac, lmode, sd).run().summary() for sd in SEEDS]
    keys = ["sess_mig_per_slot", "sess_cost_per_slot", "sess_corrupt_rate", "honest_access_ms",
            "honest_net_delay_ms", "misdirected", "wasted_cold", "accepted", "liar_flag_rate", "honest_flag_rate"]
    return {k: statistics.mean(r[k] for r in runs) for k in keys}


def save_csv(name, rows):
    with open(f"{OUT}/{name}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def save(fig, name):
    fig.tight_layout()
    fig.savefig(f"{OUT}/{name}.png", dpi=150)
    plt.close(fig)
    print("saved", f"{OUT}/{name}.png")


def sweep(lmode):
    rows = []
    for f in FRACS:
        for name, (mode, guard) in SCHEMES.items():
            r = avg(mode, guard, f, lmode)
            rows.append({"liars_%": int(f * 100), "scheme": name, **{k: round(v, 4) for k, v in r.items()}})
            print(f"{lmode} {int(f*100)}% {name}: mig/slot={r['sess_mig_per_slot']:.1f} "
                  f"corrupt={r['sess_corrupt_rate']*100:.1f}% access={r['honest_access_ms']:.2f}ms")
    return rows


def line_chart(rows, key, scale, ylabel, title, name, schemes=None):
    fig, ax = plt.subplots(figsize=(7, 4.2))
    xs = FRACS_PCT = [int(f * 100) for f in FRACS]
    for s in (schemes or SCHEMES):
        ys = [r[key] * scale for r in rows if r["scheme"] == s]
        ax.plot(xs, ys, DASH[s], marker=MARK[s], ms=8, lw=2, color=COLOR[s], label=s)
    ax.set_xticks(FRACS_PCT)
    ax.set_xlabel("vehicles lying (%)")
    ax.set_ylabel(ylabel)
    ax.set_ylim(bottom=0)
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold")
    ax.legend(fontsize=8.5)
    save(fig, name)


# 1 ------------------------------------------------------------ confidence distribution
def graph_confidence():
    honest, liars, by_type = [], [], {}
    for sd in SEEDS:
        s = sim("conf", False, 0.2, "mixed", sd)
        s.run()
        for is_liar, kind, c, _ in s.conf_log:
            (liars if is_liar else honest).append(c)
            by_type.setdefault(kind, []).append(c)
    bins = [i / 20 for i in range(21)]
    fig, ax = plt.subplots(figsize=(7, 4.2))
    for data, label, col in [(honest, "honest vehicles", "#2a78d6"), (liars, "lying vehicles", "#eb6834")]:
        w = [100.0 / len(data)] * len(data)
        ax.hist(data, bins=bins, weights=w, color=col, alpha=0.75, label=label, edgecolor=SURFACE, linewidth=1)
    ax.axvline(config.P2_CONF_USE, color=INK2, lw=1, ls="--")
    ax.text(config.P2_CONF_USE + 0.01, ax.get_ylim()[1] * 0.55, "threshold", fontsize=8.5, color=INK2)
    ax.set_xlabel("confidence score (0 - 1)")
    ax.set_ylabel("reports (%)")
    ax.set_title("Confidence separates liars from honest vehicles", loc="left", fontsize=12, fontweight="bold")
    ax.legend(fontsize=9, loc="upper left")
    save(fig, "1_confidence_distribution")
    return by_type


# 2 ------------------------------------------------------------ detection per VeReMi attack
def graph_detection(by_type):
    order = ["const_pos", "const_offset", "random_pos", "random_offset", "eventual_stop", "honest"]
    labels = ["Constant\nposition", "Constant\noffset", "Random\nposition", "Random\noffset",
              "Eventual\nstop", "Honest\n(false alarm)"]
    vals = [100.0 * sum(c < config.P2_CONF_USE for c in by_type[k]) / len(by_type[k]) for k in order]
    save_csv("2_detection_by_attack", [{"report_type": k, "flagged_%": round(v, 2)} for k, v in zip(order, vals)])
    fig, ax = plt.subplots(figsize=(8, 4.2))
    cols = ["#2a78d6"] * 5 + ["#8a8984"]
    bars = ax.bar(labels, vals, 0.6, color=cols, edgecolor=SURFACE, linewidth=2)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 1, f"{v:.0f}%", ha="center", fontsize=9, color=INK)
    ax.set_ylabel("reports flagged as false (%)")
    ax.set_ylim(0, 105)
    ax.grid(axis="x", visible=False)
    ax.set_title("Detection per VeReMi attack type", loc="left", fontsize=12, fontweight="bold")
    save(fig, "2_detection_by_attack")


# 6 ------------------------------------------------------------ honest access delay
def graph_access(rows):
    r20 = [r for r in rows if r["liars_%"] == 20]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    names = list(SCHEMES)
    vals = [next(r["honest_access_ms"] for r in r20 if r["scheme"] == n) for n in names]
    bars = ax.bar([n.replace(" (ours)", "\n(ours)").replace(" + guard", " +\nguard") for n in names], vals, 0.6,
                  color=[COLOR[n] for n in names], edgecolor=SURFACE, linewidth=2)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.15, f"{v:.1f} ms", ha="center", fontsize=9, color=INK)
    ax.set_ylabel("honest access delay (ms)")
    ax.grid(axis="x", visible=False)
    ax.set_title("Service distance for honest vehicles (20% liars)", loc="left", fontsize=12, fontweight="bold")
    save(fig, "6_honest_access_delay")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    by_type = graph_confidence()
    graph_detection(by_type)

    storm = sweep("random_pos")
    save_csv("sweep_random_position", storm)
    line_chart(storm, "sess_mig_per_slot", 1, "service migrations per slot",
               "Migration storm (random-position liars)", "3_migrations_per_slot")
    line_chart(storm, "sess_cost_per_slot", 1, "migration cost (cost units / slot)",
               "Migration cost (random-position liars)", "4_migration_cost")

    mixed = sweep("mixed")
    save_csv("sweep_mixed_attacks", mixed)
    line_chart(mixed, "sess_corrupt_rate", 100, "corrupted migrations (%)",
               "Migrations misled by false reports (all attack types)", "5_corrupted_migrations")
    graph_access(mixed)
    for r in mixed:
        r["misdirected_pct"] = 100.0 * r["misdirected"] / r["accepted"] if r["accepted"] else 0.0
    line_chart(mixed, "misdirected_pct", 1, "requests sent to unreachable RSU (%)",
               "Requests lost to false positions", "7_unreachable_requests")

    print("\n--- Headline: 40% random-position liars ---")
    for r in storm:
        if r["liars_%"] == 40:
            print(f"{r['scheme']:27s} {r['sess_mig_per_slot']:5.1f} migrations/slot  "
                  f"{r['sess_cost_per_slot']:6.1f} cost/slot  {r['sess_corrupt_rate']*100:5.1f}% corrupted  "
                  f"{r['honest_access_ms']:5.2f} ms honest access")
