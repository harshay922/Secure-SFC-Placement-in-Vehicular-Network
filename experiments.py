"""Paper-style sweeps (Fig. 5-7 pattern). Averages over SEEDS. Writes results/*.csv and *.png."""
# WHAT THIS FILE DOES: runs many simulations while changing one thing (number of time slots,
#   or number of RSUs), averages the results over several seeds, and draws graphs.
# WHY WE NEED IT: one run is noisy (random). The paper's Figs. 5-7 show trends, so we repeat
#   each point with 5 seeds, average, and plot SPAVM against two simpler versions.
# WHO USES IT: nobody imports it; run it yourself:  python experiments.py
#   It uses spavm/simulator.py and writes files into the results/ folder.
import csv  # standard library to write .csv (comma-separated) files
import os  # used to create the results folder
import statistics  # standard library; we use statistics.mean() to average
import matplotlib  # plotting library
matplotlib.use("Agg")  # "Agg" = draw to image files only, no window (works on servers); must come before pyplot
import matplotlib.pyplot as plt  # "import X as Y" = use the short name plt for matplotlib.pyplot
from spavm.simulator import Simulator  # the class that runs one full simulation

SEEDS = [1, 2, 3, 4, 5]  # list of random seeds; each point on a graph = average of these 5 runs
# dict: name shown in the legend -> extra settings given to Simulator. {} = no change (full SPAVM).
VARIANTS = {"SPAVM (SPVIR+VIMA)": {}, "SPVIR only": {"enable_vima": False},
            "No reuse": {"enable_reuse": False}}
# Which numbers from each run's summary we keep and average:
# D_total = total delay (eq. 14), D_hop = multi-hop delay (eq. 11), R_total = total cost (eq. 8),
# migrations = number of VNF moves, reuse_ratio = share of VNFs served by reuse, acceptance = share accepted.
KEYS = ["D_total", "D_hop", "R_total", "migrations", "reuse_ratio", "acceptance"]


def avg(num_rsus, num_slots, **kw):  # **kw = collect any extra named arguments into a dict kw
    # List comprehension = a short way to build a list with a loop: [expr for s in SEEDS].
    # Each run uses 4 vehicles per RSU (4 * num_rsus), same density as config.STAGES.
    runs = [Simulator(num_rsus, num_slots, 4 * num_rsus, seed=s, **kw).run().summary() for s in SEEDS]
    # Dict comprehension {k: value for k in KEYS}: for each metric, the mean over the 5 runs,
    # rounded to 4 decimals. (r[k] for r in runs) is a generator = the values one by one.
    return {k: round(statistics.mean(r[k] for r in runs), 4) for k in KEYS}


def sweep(name, xs, make_args, xlabel):
    # name = file name, xs = x-axis values, make_args = function turning x into (num_rsus, num_slots),
    # xlabel = text under the x-axis.
    rows = []  # empty list; we append one dict per (x, variant)
    for x in xs:  # each point on the x-axis
        for v, kw in VARIANTS.items():  # .items() gives (key, value) pairs: v = name, kw = settings
            res = avg(*make_args(x), **kw)  # *tuple = unpack (10, x) into two positional arguments
            rows.append(dict(x=x, variant=v, **res))  # one row: x, variant name, and all averaged metrics
            print(f"{name} x={x} {v}: {res}")  # progress message (runs can take a while)
    # "with open(...) as f" opens a file and closes it automatically at the end of the block.
    # "w" = write mode; newline="" is needed by the csv module to avoid blank lines on Windows.
    with open(f"results/{name}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))  # writer that turns dicts into CSV rows
        w.writeheader()  # first line: column names
        w.writerows(rows)  # all data lines
    fig, ax = plt.subplots(1, 3, figsize=(14, 4))  # one figure, 1 row x 3 plots; ax[0], ax[1], ax[2]
    # enumerate(list) gives (index, item): i = 0,1,2 and (k, lab) = (metric key, axis label).
    for i, (k, lab) in enumerate([("D_total", "Total delay (s)"), ("R_total", "Total cost"),
                                  ("D_hop", "Multi-hop delay (s)")]):
        for v in VARIANTS:  # looping over a dict gives its keys (the variant names)
            # y-values: metric k for every row of this variant, in x order. marker="o" draws dots.
            ax[i].plot(xs, [r[k] for r in rows if r["variant"] == v], marker="o", label=v)
        ax[i].set_xlabel(xlabel)  # x-axis title
        ax[i].set_ylabel(lab)  # y-axis title
        ax[i].grid(alpha=0.3)  # light grid lines (alpha = transparency)
        ax[i].legend(fontsize=8)  # box that names each line
    fig.tight_layout()  # adjust spacing so labels do not overlap
    fig.savefig(f"results/{name}.png", dpi=150)  # save the picture; dpi = resolution
    plt.close(fig)  # free memory used by the figure


if __name__ == "__main__":  # true only when this file is run directly, not imported
    os.makedirs("results", exist_ok=True)  # make sure the output folder exists
    # lambda = a tiny unnamed function. lambda x: (10, x) means "given x, return (10 RSUs, x slots)".
    sweep("sweep_slots", [20, 30, 40, 50], lambda x: (10, x), "time slots (10 RSUs)")      # paper Fig. 5/6a
    # here x is the number of RSUs, and slots stay fixed at 20.
    sweep("sweep_rsus", [10, 20, 30, 40], lambda x: (x, 20), "number of RSUs (20 slots)")  # Fig. 6b/7
