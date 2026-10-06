"""PHASE 1 - STEP 4: security experiments and graphs.

Compares, on the SAME requests and the SAME compromised RSUs:
    SPAVM          - the paper as published (trusts every RSU)
    SPAVM + Trust  - ours (Steps 1-3)
    Oracle         - magically knows the bad RSUs (best possible, upper bound)

Writes to results/phase1/:  CSV tables + 6 PNG graphs.
Run:  python phase1_experiments.py      (about 1-2 minutes)
"""
# =====================================================================================
# WHAT: Runs the Phase 1 security experiments and draws the graphs (7 PNGs in total,
#       graph 7 was added in Step 5) plus one CSV table per graph, in results/phase1/.
# WHY:  To show, with numbers, that trust scores (trust.py) stop compromised RSUs from
#       poisoning SFCs, how fast they learn, what it costs (delay, acceptance), and why
#       we chose RHO = 3. Every scheme is run on the SAME seeds, so the SAME requests and
#       the SAME bad RSUs - the comparison is fair.
#       Trust modes: "none" = plain SPAVM, "gate" = ours (skip RSUs with T < 0.6),
#       "oracle" = knows the truth (best case). ("quarantine" exists in the simulator
#       but is not plotted here.)
# WHO USES IT: You, from the command line: python3 phase1_experiments.py
#       It uses spavm/simulator.py (which uses attacker.py and trust.py) and config.py.
#
# GRAPHS PRODUCED:
#   1_poisoned_over_time        % of SFCs poisoned in each slot -> how fast trust learns.
#   2_poisoned_vs_attacker_share % poisoned when 0,10,20,30,40% of RSUs are bad.
#   3_attacker_types            % poisoned for always-bad, on-off, stealthy attackers.
#   4_trust_trajectories        T of every RSU over time in one on-off run.
#   5_price_of_security         extra delay and lost acceptance caused by the trust gate.
#   6_rho_tradeoff              effect of RHO on safety vs. wrongly blocked honest RSUs.
#   7_sharing_limit             Step 5 idea (limit sharing on low-trust RSUs): is it worth it?
# =====================================================================================
import csv          # standard library module to write .csv tables (open in Excel)
import os           # operating-system helpers; used to create the output folder
import statistics   # standard library; statistics.mean(...) gives the average
import matplotlib   # the plotting library
# "Agg" = draw into image files only, with no window. Must be set BEFORE importing pyplot.
# This lets the script run on a server with no screen.
matplotlib.use("Agg")
# "import X as Y" gives a short nickname. plt is the usual name for pyplot (the drawing API).
import matplotlib.pyplot as plt
import config                           # our settings; we temporarily change some values (setcfg)
# "from module import Name" brings just that one class into this file.
from spavm.simulator import Simulator

# Constants (ALL CAPS by convention = "do not change while running").
OUT = "results/phase1"                  # folder where CSVs and PNGs go
SEEDS = [1, 2, 3, 4, 5]                 # 5 random seeds; results are averaged over them
# Multiple assignment: three names get three values in one line.
N_RSU, N_SLOTS, N_VEH = 10, 50, 40          # paper scenario 1 size, 50 slots
# A dict (dictionary) maps a key to a value: here "label shown on graph" -> trust mode name.
SCHEMES = {"SPAVM (no trust)": "none", "SPAVM + Trust (ours)": "gate", "Oracle (knows attackers)": "oracle"}

# ---- chart style: validated palette, thin marks, recessive grid, one axis per chart ----
# Colours are hex codes "#RRGGBB". SURFACE = background, INK = main text, INK2 = soft text.
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
# One fixed colour, marker shape and line style per scheme, so every graph matches.
COLOR = {"SPAVM (no trust)": "#eb6834", "SPAVM + Trust (ours)": "#2a78d6", "Oracle (knows attackers)": "#1baf7a"}
# Marker codes: "o" circle, "s" square, "^" triangle.
MARK = {"SPAVM (no trust)": "o", "SPAVM + Trust (ours)": "s", "Oracle (knows attackers)": "^"}
# Line styles: "-" solid, "--" dashed (Oracle is dashed because it is a reference, not a real scheme).
DASH = {"SPAVM (no trust)": "-", "SPAVM + Trust (ours)": "-", "Oracle (knows attackers)": "--"}
# plt.rcParams is matplotlib's global style settings; .update(...) changes many at once.
# This sets background colours, grid, font size, and hides the top/right box lines.
plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "axes.edgecolor": GRID,
                     "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "text.color": INK,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "font.size": 10,
                     "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False})


# Temporarily change config values, e.g. setcfg(RHO=5.0). Returns the OLD values so we can undo.
# "**kw" collects any keyword arguments into a dict: setcfg(RHO=5.0) -> kw = {"RHO": 5.0}.
def setcfg(**kw):
    # getattr(config, "RHO") reads config.RHO by its name as a string.
    # This dict comprehension saves the current value of every setting we are about to change.
    old = {k: getattr(config, k) for k in kw}
    # .items() gives (key, value) pairs; "for k, v in ..." unpacks each pair into two names.
    for k, v in kw.items():
        # setattr(config, "RHO", 5.0) is the same as writing config.RHO = 5.0.
        setattr(config, k, v)
    return old


# Run ONE simulation. mode = trust mode ("none"/"gate"/"oracle"), frac = share of bad RSUs,
# amode = attack mode, seed = random seed, **cfg = any config overrides (e.g. P_TAMPER=0.2).
def run(mode, frac=0.2, amode="always", seed=1, **cfg):
    # Apply the overrides and remember the old values.
    old = setcfg(**cfg)
    # Build the simulator (keyword arguments name=value make the call easy to read).
    s = Simulator(N_RSU, N_SLOTS, N_VEH, seed=seed, attack_fraction=frac, attack_mode=amode, trust_mode=mode)
    # Run all slots. m holds the per-slot metrics.
    m = s.run()
    # Put config back so the next run is not affected.
    setcfg(**old)
    # Return two values at once (a tuple); the caller writes "s, m = run(...)".
    return s, m


# Run the same setting on all 5 seeds and average the summary numbers.
def avg(mode, **kw):
    """Average summary over all seeds."""
    rows = []   # empty list; we append one summary dict per seed
    for sd in SEEDS:
        # "**kw" here does the opposite of above: it spreads the dict back into name=value arguments.
        s, m = run(mode, seed=sd, **kw)
        # m.summary() -> dict of performance numbers (delay, acceptance, poisoned_rate, ...).
        r = m.summary()
        # .update(...) merges the security numbers (false blocks, detect slot, ...) into the same dict.
        r.update(s.security_summary())
        # .append adds one item to the end of the list.
        rows.append(r)
    # The numbers we want to average.
    keys = ["poisoned_rate", "secure_rate", "avg_delay_per_request", "acceptance", "false_block_share", "cold", "probes"]
    # For each key, the mean over seeds. "r[k] for r in rows" is a generator: values one by one.
    out = {k: statistics.mean(r[k] for r in rows) for k in keys}
    # avg_detect_slot can be None (e.g. no attackers were ever detected), so keep only real numbers.
    # This is a list comprehension with a filter: [x for r in rows if condition].
    det = [r["avg_detect_slot"] for r in rows if r["avg_detect_slot"] is not None]
    # An empty list counts as False, so: mean if we have values, else None.
    out["avg_detect_slot"] = statistics.mean(det) if det else None
    return out


# Write a list of dicts to results/phase1/<name>.csv (one dict = one row).
def save_csv(name, rows):
    # f"..." is an f-string: {OUT} and {name} are replaced by their values.
    # "with open(...) as f:" opens the file and closes it automatically when the block ends.
    # "w" = write mode; newline="" avoids blank lines between rows on Windows.
    with open(f"{OUT}/{name}.csv", "w", newline="") as f:
        # DictWriter writes dicts as rows; the column names come from the first row's keys.
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()     # first line: column names
        w.writerows(rows)   # then all data rows


# Shared last step for single-panel graphs: title, subtitle, save to PNG, close.
# fig = the whole image, ax = the one plotting area inside it (see graph 1 for more).
def finish(fig, ax, name, title, sub):
    # Bold title aligned left; pad=22 leaves room for the subtitle under it.
    ax.set_title(title, loc="left", fontsize=12, color=INK, pad=22, fontweight="bold")
    # Subtitle text. transform=ax.transAxes means (0, 1.02) is in "axes units":
    # x=0 is the left edge, y=1.02 is just above the top of the plot area.
    ax.text(0, 1.02, sub, transform=ax.transAxes, fontsize=9, color=INK2)
    # Auto-adjust spacing so labels are not cut off.
    fig.tight_layout()
    # savefig writes the image file. dpi = dots per inch (150 = sharp enough for slides).
    fig.savefig(f"{OUT}/{name}.png", dpi=150)
    # Free the memory used by this figure (important when making many graphs).
    plt.close(fig)
    print("saved", f"{OUT}/{name}.png")


# 1 --------------------------------------------------------------- over time
# GRAPH 1: For each slot, % of accepted SFCs that were poisoned (tampered), averaged over seeds,
# one line per scheme. Shows: SPAVM stays high all the time; with trust the line drops to ~0
# within a few slots (the time trust needs to collect N_MIN evidence and catch the bad RSUs).
def graph_over_time():
    # Two empty containers in one line: series = dict (scheme -> list of values), rows = list.
    series, rows = {}, []
    for name, mode in SCHEMES.items():
        # One list of N_SLOTS zeros per seed (a list of lists). "_" = a loop variable we don't use.
        per = [[0.0] * N_SLOTS for _ in SEEDS]
        # enumerate gives (index, value): i = 0,1,2,... and sd = the seed.
        for i, sd in enumerate(SEEDS):
            # "_, m = ..." ignores the first returned value (the simulator), keeps metrics m.
            _, m = run(mode, seed=sd)
            # m.rows = one dict per slot. Poisoned % = poisoned / accepted * 100,
            # or 0 if nothing was accepted in that slot (avoids dividing by zero).
            per[i] = [r["poisoned"] / r["accepted"] * 100 if r["accepted"] else 0 for r in m.rows]
        # Average across seeds for each slot t: p[t] for every seed's list p.
        series[name] = [statistics.mean(p[t] for p in per) for t in range(N_SLOTS)]
    # Build CSV rows: {"slot": t, "SPAVM (no trust)": ..., "SPAVM + Trust (ours)": ..., ...}.
    # "**{...}" inside a dict literal copies all pairs of another dict into this one.
    for t in range(N_SLOTS):
        rows.append({"slot": t, **{k: round(v[t], 2) for k, v in series.items()}})
    save_csv("1_poisoned_over_time", rows)
    # MATPLOTLIB BASICS:
    #   plt.subplots() creates a figure (fig = the whole image/page) and an axes
    #   (ax = one chart area with x and y axes). figsize = (width, height) in inches.
    #   We then draw on ax (ax.plot, ax.bar, ...) and save the figure with fig.savefig (in finish()).
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for name, ys in series.items():
        # ax.plot(x_values, y_values, style, ...) draws a line. range(N_SLOTS) = 0..49 on the x-axis.
        # color = line colour, lw = line width, label = text shown in the legend.
        ax.plot(range(N_SLOTS), ys, DASH[name], color=COLOR[name], lw=2, label=name)
    # [-1] means "last item": SPAVM's poisoned % in the final slot.
    spavm_end = series["SPAVM (no trust)"][-1]
    # ax.annotate writes text at a data point. {spavm_end:.0f} formats the number with 0 decimals.
    # xytext=(6, 0) with textcoords="offset points" shifts the text 6 points to the right.
    ax.annotate(f"SPAVM {spavm_end:.0f}%", (N_SLOTS - 1, spavm_end), xytext=(6, 0),
                textcoords="offset points", va="center", fontsize=8.5, color=INK)
    ax.annotate("Trust and Oracle ≈ 0%", (N_SLOTS - 1, 0), xytext=(6, 8),
                textcoords="offset points", va="bottom", fontsize=8.5, color=INK)
    ax.set_xlabel("time slot")                      # x-axis title
    ax.set_ylabel("SFCs poisoned in the slot (%)")  # y-axis title
    ax.set_xlim(0, N_SLOTS + 12)                    # extra room on the right for the annotations
    ax.set_ylim(bottom=0)                           # y-axis starts at 0
    ax.legend(loc="upper right", fontsize=8.5)      # show the labels given in ax.plot(label=...)
    finish(fig, ax, "1_poisoned_over_time", "Trust learns within a few slots",
           f"{N_RSU} RSUs, 20% compromised (always-bad), average of {len(SEEDS)} seeds")


# 2 --------------------------------------------------------------- vs attacker share
# GRAPH 2: Overall % of SFCs poisoned (whole run, averaged over seeds) as the share of
# compromised RSUs grows 0% -> 40%. Shows: SPAVM gets much worse with more attackers,
# trust stays close to the Oracle. Also returns its rows, reused by graph 5 (price of security).
def graph_vs_fraction():
    fracs = [0.0, 0.1, 0.2, 0.3, 0.4]   # share of bad RSUs to test
    rows = []
    for f in fracs:
        for name, mode in SCHEMES.items():
            r = avg(mode, frac=f)
            # One CSV row: attacker %, scheme, then every averaged number (rounded to 4 decimals,
            # or "" if the value is None, so the CSV cell is empty).
            rows.append({"attackers_%": int(f * 100), "scheme": name, **{k: (round(v, 4) if v is not None else "") for k, v in r.items()}})
    save_csv("2_vs_attacker_share", rows)
    fig, ax = plt.subplots(figsize=(8, 4.2))
    # x positions as whole percentages: [0, 10, 20, 30, 40]. int(...) drops the decimal part.
    xs = [int(f * 100) for f in fracs]
    # Looping over a dict gives its keys (the scheme labels).
    for name in SCHEMES:
        # Pick this scheme's rows (in order of fracs) and convert rate 0..1 into %.
        ys = [r["poisoned_rate"] * 100 for r in rows if r["scheme"] == name]
        # marker = point shape, ms = marker size.
        ax.plot(xs, ys, DASH[name], marker=MARK[name], ms=8, color=COLOR[name], lw=2, label=name)
        # Label the last point (40%) with its value, 1 decimal place.
        ax.annotate(f"{ys[-1]:.1f}%", (xs[-1], ys[-1]), xytext=(8, 0), textcoords="offset points",
                    va="center", fontsize=8.5, color=INK)
    ax.set_xlabel("compromised RSUs (%)")
    ax.set_ylabel("SFCs poisoned (%)")
    ax.set_xticks(xs)                # put tick marks exactly at 0, 10, 20, 30, 40
    ax.set_xlim(-2, 46)              # a little padding on both sides
    ax.set_ylim(bottom=0)
    ax.legend(loc="upper left", fontsize=8.5)
    finish(fig, ax, "2_poisoned_vs_attacker_share", "More attackers hurt SPAVM badly; trust stays low",
           f"{N_RSU} RSUs, {N_SLOTS} slots, always-bad attackers, average of {len(SEEDS)} seeds")
    # Give the rows back to the caller (the main block passes them to graph_price).
    return rows


# 3 --------------------------------------------------------------- attacker types
# GRAPH 3: Grouped bar chart. For each attacker type (always-bad, on-off, stealthy with
# P_TAMPER 0.2) it shows % of SFCs poisoned for SPAVM vs SPAVM + Trust. Shows: trust helps
# against every type, including the harder on-off and stealthy attackers.
def graph_attacker_types():
    # dict(amode="always") is another way to write {"amode": "always"}.
    # "\n" inside a string is a line break (so the bar label uses two lines).
    cases = {"Always-bad": dict(amode="always"), "On-off": dict(amode="onoff"),
             "Stealthy\n(tampers 20%)": dict(amode="always", P_TAMPER=0.2)}
    rows = []
    for label, kw in cases.items():
        # list(...)[:2] = the first 2 schemes only (SPAVM and ours; Oracle is skipped here).
        # "[:2]" is slicing: items from the start up to (not including) index 2.
        for name, mode in list(SCHEMES.items())[:2]:
            r = avg(mode, **kw)
            # .replace("\n", " ") removes the line break for the CSV.
            # detect_slot = average slot at which bad RSUs were first blocked ("" if never).
            rows.append({"attacker": label.replace("\n", " "), "scheme": name,
                         "poisoned_%": round(r["poisoned_rate"] * 100, 2),
                         "detect_slot": round(r["avg_detect_slot"], 1) if r["avg_detect_slot"] is not None else ""})
    save_csv("3_attacker_types", rows)
    fig, ax = plt.subplots(figsize=(8, 4.2))
    # labels = the case names; w = width of each bar.
    labels, w = list(cases), 0.36
    for j, name in enumerate(list(SCHEMES)[:2]):
        ys = [r["poisoned_%"] for r in rows if r["scheme"] == name]
        # Shift bars left (j=0) or right (j=1) of each group centre i, with a small gap of 0.03.
        xs = [i + (j - 0.5) * (w + 0.03) for i in range(len(labels))]
        # ax.bar(x, heights, width, ...) draws bars and returns them so we can label each one.
        bars = ax.bar(xs, ys, w, color=COLOR[name], label=name, edgecolor=SURFACE, linewidth=2)
        # zip pairs up two lists item by item: (bar1, y1), (bar2, y2), ...
        for b, y in zip(bars, ys):
            # Write the value just above the middle of each bar.
            ax.text(b.get_x() + b.get_width() / 2, y + 0.4, f"{y:.1f}%", ha="center", fontsize=8.5, color=INK)
    ax.set_xticks(range(len(labels)))   # one tick per group centre: 0, 1, 2
    ax.set_xticklabels(labels)          # and name them with the attacker type
    ax.set_ylabel("SFCs poisoned (%)")
    ax.grid(axis="x", visible=False)    # hide vertical grid lines (not useful for bars)
    ax.legend(loc="upper right", fontsize=8.5)
    finish(fig, ax, "3_attacker_types", "Trust works against every attacker type",
           f"{N_RSU} RSUs, 20% compromised, {N_SLOTS} slots, average of {len(SEEDS)} seeds")


# 4 --------------------------------------------------------------- trust trajectories
# GRAPH 4: One run (seed 2, on-off attacker, gate mode). One line per RSU showing its trust
# score T over time. Bad RSUs = solid orange, honest = dotted blue; shaded bands = the attacker's
# "bad" periods; dashed line = threshold 0.6. Shows: bad RSUs drop fast when they attack and
# climb back only slowly in their "good" periods (because RHO = 3), so they stay mostly blocked.
def graph_trust_trajectories():
    s, _ = run("gate", amode="onoff", seed=2)
    # trust_log = list with one row per slot; each row = list of T values, one per RSU.
    log = s.trust_log
    fig, ax = plt.subplots(figsize=(8, 4.2))
    honest_c, bad_c = "#2a78d6", "#eb6834"
    for r in range(N_RSU):
        bad = s.attacker.is_malicious(r)    # True/False: is RSU r compromised?
        # [row[r] for row in log] = RSU r's T in every slot.
        # Style depends on bad: solid & thick & opaque for bad RSUs, dotted & thin & faded for honest.
        # alpha = opacity (1 = solid, 0 = invisible).
        ax.plot(range(len(log)), [row[r] for row in log], "-" if bad else ":",
                color=bad_c if bad else honest_c, lw=2 if bad else 1.2, alpha=1 if bad else 0.7,
                label=("compromised RSU (on-off)" if bad else "honest RSU"))
    # range(start, stop, step): k = 1, 3, 5, 7, 9 -> the odd blocks, i.e. the "bad" periods.
    for k in range(1, N_SLOTS // config.ONOFF_PERIOD, 2):
        # axvspan shades a vertical band from x1 to x2. zorder=0 puts it behind the lines.
        ax.axvspan(k * config.ONOFF_PERIOD, (k + 1) * config.ONOFF_PERIOD, color="#f1efe9", zorder=0)
    # axhline draws a horizontal line across the chart at y = 0.6 (the gate threshold).
    ax.axhline(config.TRUST_THETA, color=INK2, lw=1, ls="--")
    ax.text(1, config.TRUST_THETA - 0.05, f"threshold θ = {config.TRUST_THETA}", ha="left", fontsize=8.5, color=INK2)
    # Every RSU line has a label, so the legend would repeat "honest RSU" many times.
    # h = line handles, l = their labels. dict(zip(l, h)) keeps one handle per unique label.
    h, l = ax.get_legend_handles_labels()
    uniq = dict(zip(l, h))
    ax.legend(uniq.values(), uniq.keys(), loc="lower left", fontsize=8.5)
    ax.set_xlabel("time slot   (shaded = attacker's 'bad' periods)")
    ax.set_ylabel("trust score T")
    ax.set_ylim(0, 1)   # T is always between 0 and 1
    # CSV: one row per slot; columns named "RSU0", "RSU1_BAD", ... (suffix _BAD for compromised).
    # Nested comprehension: outer over slots (t, row), inner over RSUs (r, v).
    save_csv("4_trust_trajectories", [{"slot": t, **{f"RSU{r}{'_BAD' if s.attacker.is_malicious(r) else ''}": round(v, 3)
                                                      for r, v in enumerate(row)}} for t, row in enumerate(log)])
    finish(fig, ax, "4_trust_trajectories", "Bad RSUs lose trust fast and regain it only slowly",
           "one run (seed 2), on-off attacker: good for 5 slots, bad for 5 slots")


# 5 --------------------------------------------------------------- price of security
# GRAPH 5: Two panels, reusing graph 2's rows (no new simulations). Left: average delay per
# request (ms) vs % attackers. Right: % of requests accepted. Shows the cost of security:
# skipping untrusted RSUs means less container reuse, so a bit more delay and a bit less acceptance.
def graph_price(rows):
    # plt.subplots(1, 2, ...) = 1 row, 2 columns of charts. axes is a list: axes[0] left, axes[1] right.
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    # A set {...} removes duplicates (each % appears once per scheme); sorted(...) orders them.
    xs = sorted({r["attackers_%"] for r in rows})
    for name in SCHEMES:
        # Delay in seconds * 1000 = milliseconds.
        d = [r["avg_delay_per_request"] * 1000 for r in rows if r["scheme"] == name]
        # Acceptance 0..1 * 100 = percent.
        a = [r["acceptance"] * 100 for r in rows if r["scheme"] == name]
        axes[0].plot(xs, d, DASH[name], marker=MARK[name], ms=8, color=COLOR[name], lw=2, label=name)
        axes[1].plot(xs, a, DASH[name], marker=MARK[name], ms=8, color=COLOR[name], lw=2, label=name)
    axes[0].set_ylabel("average delay per request (ms)")
    axes[1].set_ylabel("requests accepted (%)")
    axes[0].set_ylim(bottom=0)
    axes[1].set_ylim(80, 100)   # zoom in on 80-100% so small differences are visible
    # Same x settings for both panels.
    for ax in axes:
        ax.set_xlabel("compromised RSUs (%)")
        ax.set_xticks(xs)
    axes[0].legend(loc="lower left", fontsize=8)
    axes[0].set_title("Delay", loc="left", fontsize=11, fontweight="bold")
    axes[1].set_title("Acceptance", loc="left", fontsize=11, fontweight="bold")
    # suptitle = one title for the whole figure (above both panels). x=0.01, ha="left" = left-aligned.
    fig.suptitle("The price of security: at 40% attackers, ~7% more delay and ~2% fewer requests accepted",
                 x=0.01, ha="left", fontsize=12, fontweight="bold")
    # Two panels, so we save here instead of calling finish() (which handles one ax only).
    fig.tight_layout()
    fig.savefig(f"{OUT}/5_price_of_security.png", dpi=150)
    plt.close(fig)
    print("saved", f"{OUT}/5_price_of_security.png")


# 6 --------------------------------------------------------------- why rho > 1
# GRAPH 6: Runs our scheme against the on-off attacker with RHO = 1, 2, 3, 5.
# Left panel: % SFCs poisoned (safety). Right panel: % of honest RSUs wrongly blocked (fairness).
# Shows the trade-off: RHO too small lets on-off attackers rebuild trust; RHO too big punishes
# honest RSUs for their small random faults. RHO = 3 is the chosen balance.
def graph_rho():
    rhos = [1.0, 2.0, 3.0, 5.0]
    rows = []
    for rh in rhos:
        # RHO=rh is passed through avg -> run -> setcfg, which temporarily sets config.RHO.
        r = avg("gate", amode="onoff", RHO=rh)
        rows.append({"rho": rh, "poisoned_%": round(r["poisoned_rate"] * 100, 2),
                     "false_block_%": round(r["false_block_share"] * 100, 2)})
    save_csv("6_rho_tradeoff", rows)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    # Bar labels like "ρ = 3". int(r) turns 3.0 into 3.
    labels = [f"ρ = {int(r)}" for r in rhos]
    # Loop over the two panels. Each tuple = (which axes, which CSV column, panel title, colour).
    for ax, key, title, col in [(axes[0], "poisoned_%", "SFCs poisoned (%)  - lower is safer", "#2a78d6"),
                                (axes[1], "false_block_%", "Honest RSUs wrongly blocked (%)  - lower is fairer", "#2a78d6")]:
        ys = [r[key] for r in rows]
        # Text labels can be used directly as x positions for bars. 0.55 = bar width.
        bars = ax.bar(labels, ys, 0.55, color=col, edgecolor=SURFACE, linewidth=2)
        for b, y in zip(bars, ys):
            # va="bottom" puts the bottom of the text at the top of the bar.
            ax.text(b.get_x() + b.get_width() / 2, y, f"{y:.2f}", ha="center", va="bottom", fontsize=8.5, color=INK)
        ax.set_title(title, loc="left", fontsize=10.5, fontweight="bold")
        ax.grid(axis="x", visible=False)
        ax.set_xlabel("how much more bad evidence counts than good")
    fig.suptitle("Choosing ρ (on-off attacker): ρ = 3 poisons fewest SFCs; higher ρ blocks too many honest RSUs",
                 x=0.01, ha="left", fontsize=12, fontweight="bold")
    fig.tight_layout()
    fig.savefig(f"{OUT}/6_rho_tradeoff.png", dpi=150)
    plt.close(fig)
    print("saved", f"{OUT}/6_rho_tradeoff.png")


# 7 --------------------------------------------------------------- Step 5: sharing limit
# Helper for graph 7: average poisoned % and delay (ms) over all seeds for our "gate" scheme,
# with the Step 5 sharing limit on (share=True) or off (share=False).
def avg_share(share, **kw):
    """Like avg('gate'), but toggling the Step 5 trust-based sharing limit."""
    # kw.pop("amode", "always") removes "amode" from kw and returns it (or "always" if missing).
    # We remove them so that only real config names remain in kw for setcfg.
    amode, frac = kw.pop("amode", "always"), kw.pop("frac", 0.2)
    old = setcfg(**kw)
    res = []
    for sd in SEEDS:
        # A long call can continue on the next line while inside the brackets.
        s = Simulator(N_RSU, N_SLOTS, N_VEH, seed=sd, attack_fraction=frac, attack_mode=amode,
                      trust_mode="gate", share_limit=share)
        # Method chaining: run the simulation, then immediately take its summary.
        r = s.run().summary()
        # Append a pair (tuple): (poisoned %, delay in ms).
        res.append((r["poisoned_rate"] * 100, r["avg_delay_per_request"] * 1000))
    setcfg(**old)
    # x[0] = first item of each pair, x[1] = second. Returns two averages.
    return statistics.mean(x[0] for x in res), statistics.mean(x[1] for x in res)


# GRAPH 7: Step 5 idea - on low-trust RSUs, limit how many SFCs may share one container.
# Two panels of grouped bars for 4 attacker cases: left = % poisoned, right = delay (ms),
# each without / with the sharing limit. Shows: the limit barely lowers poisoning (and is
# worse for on-off) but adds a lot of delay, so the plain trust gate is the better design.
def graph_sharing_limit():
    # {} = no overrides (default always-bad, 20%). Other cases change one thing each.
    cases = {"Always-bad": {}, "On-off": {"amode": "onoff"}, "Stealthy": {"P_TAMPER": 0.2},
             "40% attackers": {"frac": 0.4}}
    # Dicts can use True/False as keys: map the share flag to a label and a colour.
    names = {False: "SPAVM + Trust (ours)", True: "+ trust-based sharing limit"}
    cols = {False: "#2a78d6", True: "#eda100"}
    rows = []
    for label, kw in cases.items():
        # (False, True) is a tuple; loop runs once without and once with the limit.
        for share in (False, True):
            # dict(kw) passes a COPY, because avg_share's .pop would otherwise change our cases dict.
            p, d = avg_share(share, **dict(kw))
            rows.append({"attacker": label, "scheme": names[share], "poisoned_%": round(p, 2), "delay_ms": round(d, 1)})
    save_csv("7_sharing_limit", rows)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    labels, w = list(cases), 0.38
    # One loop pass per panel: (axes, CSV column, title, number format for bar labels).
    for ax, key, title, fmt in [(axes[0], "poisoned_%", "SFCs poisoned (%)  - lower is safer", "{:.2f}"),
                                (axes[1], "delay_ms", "Average delay per request (ms)", "{:.0f}")]:
        for j, share in enumerate((False, True)):
            ys = [r[key] for r in rows if r["scheme"] == names[share]]
            # Same side-by-side bar trick as graph 3.
            xs = [i + (j - 0.5) * (w + 0.03) for i in range(len(labels))]
            bars = ax.bar(xs, ys, w, color=cols[share], label=names[share], edgecolor=SURFACE, linewidth=2)
            for b, y in zip(bars, ys):
                # fmt.format(y) fills the "{:.2f}" or "{:.0f}" pattern with the value y.
                ax.text(b.get_x() + b.get_width() / 2, y, fmt.format(y), ha="center", va="bottom",
                        fontsize=8, color=INK)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, fontsize=9)
        ax.set_title(title, loc="left", fontsize=10.5, fontweight="bold")
        ax.grid(axis="x", visible=False)
    axes[0].legend(loc="upper left", fontsize=8.5)
    fig.suptitle("Step 5 result: sharing limit barely helps (worse for on-off) and adds ~30-45% delay",
                 x=0.01, ha="left", fontsize=12, fontweight="bold")
    fig.tight_layout()
    fig.savefig(f"{OUT}/7_sharing_limit.png", dpi=150)
    plt.close(fig)
    print("saved", f"{OUT}/7_sharing_limit.png")


# This block runs only when the file is started directly (python3 phase1_experiments.py),
# not when another file imports it (e.g. a test). __name__ is "__main__" only in the first case.
if __name__ == "__main__":
    # Create results/phase1/ if missing; exist_ok=True means "no error if it already exists".
    os.makedirs(OUT, exist_ok=True)
    graph_over_time()
    # Keep graph 2's rows: graph 5 and the headline print below reuse them.
    frac_rows = graph_vs_fraction()
    graph_attacker_types()
    graph_trust_trajectories()
    graph_price(frac_rows)
    graph_rho()
    graph_sharing_limit()
    # "\n" at the start prints an empty line first.
    print("\n--- Headline (20% compromised, always-bad) ---")
    # Print one summary line per scheme for the 20% case (the default test level).
    for r in frac_rows:
        if r["attackers_%"] == 20:
            # Format codes: {x:26s} = text padded to 26 characters, {x:5.1f} = number 5 wide, 1 decimal.
            # Two f-strings side by side are joined into one string automatically.
            print(f"{r['scheme']:26s} poisoned={r['poisoned_rate']*100:5.1f}%  delay={r['avg_delay_per_request']*1000:6.1f} ms  "
                  f"accepted={r['acceptance']*100:5.1f}%  honest wrongly blocked={r['false_block_share']*100:4.1f}%")
