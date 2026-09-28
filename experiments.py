"""Paper-style sweeps (Fig. 5-7 pattern). Averages over SEEDS. Writes results/*.csv and *.png."""
import csv
import os
import statistics
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from spavm.simulator import Simulator

SEEDS = [1, 2, 3, 4, 5]
VARIANTS = {"SPAVM (SPVIR+VIMA)": {}, "SPVIR only": {"enable_vima": False},
            "No reuse": {"enable_reuse": False}}
KEYS = ["D_total", "D_hop", "R_total", "migrations", "reuse_ratio", "acceptance"]


def avg(num_rsus, num_slots, **kw):
    runs = [Simulator(num_rsus, num_slots, 4 * num_rsus, seed=s, **kw).run().summary() for s in SEEDS]
    return {k: round(statistics.mean(r[k] for r in runs), 4) for k in KEYS}


def sweep(name, xs, make_args, xlabel):
    rows = []
    for x in xs:
        for v, kw in VARIANTS.items():
            res = avg(*make_args(x), **kw)
            rows.append(dict(x=x, variant=v, **res))
            print(f"{name} x={x} {v}: {res}")
    with open(f"results/{name}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    fig, ax = plt.subplots(1, 3, figsize=(14, 4))
    for i, (k, lab) in enumerate([("D_total", "Total delay (s)"), ("R_total", "Total cost"),
                                  ("D_hop", "Multi-hop delay (s)")]):
        for v in VARIANTS:
            ax[i].plot(xs, [r[k] for r in rows if r["variant"] == v], marker="o", label=v)
        ax[i].set_xlabel(xlabel)
        ax[i].set_ylabel(lab)
        ax[i].grid(alpha=0.3)
        ax[i].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(f"results/{name}.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    os.makedirs("results", exist_ok=True)
    sweep("sweep_slots", [20, 30, 40, 50], lambda x: (10, x), "time slots (10 RSUs)")      # paper Fig. 5/6a
    sweep("sweep_rsus", [10, 20, 30, 40], lambda x: (x, 20), "number of RSUs (20 slots)")  # Fig. 6b/7
