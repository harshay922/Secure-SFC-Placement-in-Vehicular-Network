"""PHASE 1 - STEP 4: security experiments and graphs.

Compares, on the SAME requests and the SAME compromised RSUs:
    SPAVM          - the paper as published (trusts every RSU)
    SPAVM + Trust  - ours (Steps 1-3)
    Oracle         - magically knows the bad RSUs (best possible, upper bound)

Writes to results/phase1/:  CSV tables + 6 PNG graphs.
Run:  python phase1_experiments.py      (about 1-2 minutes)
"""
import csv
import os
import statistics
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import config
from spavm.simulator import Simulator

OUT = "results/phase1"
SEEDS = [1, 2, 3, 4, 5]
N_RSU, N_SLOTS, N_VEH = 10, 50, 40          # paper scenario 1 size, 50 slots
SCHEMES = {"SPAVM (no trust)": "none", "SPAVM + Trust (ours)": "gate", "Oracle (knows attackers)": "oracle"}

# ---- chart style: validated palette, thin marks, recessive grid, one axis per chart ----
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
COLOR = {"SPAVM (no trust)": "#eb6834", "SPAVM + Trust (ours)": "#2a78d6", "Oracle (knows attackers)": "#1baf7a"}
MARK = {"SPAVM (no trust)": "o", "SPAVM + Trust (ours)": "s", "Oracle (knows attackers)": "^"}
DASH = {"SPAVM (no trust)": "-", "SPAVM + Trust (ours)": "-", "Oracle (knows attackers)": "--"}
plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "axes.edgecolor": GRID,
                     "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "text.color": INK,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "font.size": 10,
                     "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False})


def setcfg(**kw):
    old = {k: getattr(config, k) for k in kw}
    for k, v in kw.items():
        setattr(config, k, v)
    return old


def run(mode, frac=0.2, amode="always", seed=1, **cfg):
    old = setcfg(**cfg)
    s = Simulator(N_RSU, N_SLOTS, N_VEH, seed=seed, attack_fraction=frac, attack_mode=amode, trust_mode=mode)
    m = s.run()
    setcfg(**old)
    return s, m


def avg(mode, **kw):
    """Average summary over all seeds."""
    rows = []
    for sd in SEEDS:
        s, m = run(mode, seed=sd, **kw)
        r = m.summary()
        r.update(s.security_summary())
        rows.append(r)
    keys = ["poisoned_rate", "secure_rate", "avg_delay_per_request", "acceptance", "false_block_share", "cold", "probes"]
    out = {k: statistics.mean(r[k] for r in rows) for k in keys}
    det = [r["avg_detect_slot"] for r in rows if r["avg_detect_slot"] is not None]
    out["avg_detect_slot"] = statistics.mean(det) if det else None
    return out


def save_csv(name, rows):
    with open(f"{OUT}/{name}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def finish(fig, ax, name, title, sub):
    ax.set_title(title, loc="left", fontsize=12, color=INK, pad=22, fontweight="bold")
    ax.text(0, 1.02, sub, transform=ax.transAxes, fontsize=9, color=INK2)
    fig.tight_layout()
    fig.savefig(f"{OUT}/{name}.png", dpi=150)
    plt.close(fig)
    print("saved", f"{OUT}/{name}.png")


# 1 --------------------------------------------------------------- over time
def graph_over_time():
    series, rows = {}, []
    for name, mode in SCHEMES.items():
        per = [[0.0] * N_SLOTS for _ in SEEDS]
        for i, sd in enumerate(SEEDS):
            _, m = run(mode, seed=sd)
            per[i] = [r["poisoned"] / r["accepted"] * 100 if r["accepted"] else 0 for r in m.rows]
        series[name] = [statistics.mean(p[t] for p in per) for t in range(N_SLOTS)]
    for t in range(N_SLOTS):
        rows.append({"slot": t, **{k: round(v[t], 2) for k, v in series.items()}})
    save_csv("1_poisoned_over_time", rows)
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for name, ys in series.items():
        ax.plot(range(N_SLOTS), ys, DASH[name], color=COLOR[name], lw=2, label=name)
    spavm_end = series["SPAVM (no trust)"][-1]
    ax.annotate(f"SPAVM {spavm_end:.0f}%", (N_SLOTS - 1, spavm_end), xytext=(6, 0),
                textcoords="offset points", va="center", fontsize=8.5, color=INK)
    ax.annotate("Trust and Oracle ≈ 0%", (N_SLOTS - 1, 0), xytext=(6, 8),
                textcoords="offset points", va="bottom", fontsize=8.5, color=INK)
    ax.set_xlabel("time slot")
    ax.set_ylabel("SFCs poisoned in the slot (%)")
    ax.set_xlim(0, N_SLOTS + 12)
    ax.set_ylim(bottom=0)
    ax.legend(loc="upper right", fontsize=8.5)
    finish(fig, ax, "1_poisoned_over_time", "Trust learns within a few slots",
           f"{N_RSU} RSUs, 20% compromised (always-bad), average of {len(SEEDS)} seeds")


# 2 --------------------------------------------------------------- vs attacker share
def graph_vs_fraction():
    fracs = [0.0, 0.1, 0.2, 0.3, 0.4]
    rows = []
    for f in fracs:
        for name, mode in SCHEMES.items():
            r = avg(mode, frac=f)
            rows.append({"attackers_%": int(f * 100), "scheme": name, **{k: (round(v, 4) if v is not None else "") for k, v in r.items()}})
    save_csv("2_vs_attacker_share", rows)
    fig, ax = plt.subplots(figsize=(8, 4.2))
    xs = [int(f * 100) for f in fracs]
    for name in SCHEMES:
        ys = [r["poisoned_rate"] * 100 for r in rows if r["scheme"] == name]
        ax.plot(xs, ys, DASH[name], marker=MARK[name], ms=8, color=COLOR[name], lw=2, label=name)
        ax.annotate(f"{ys[-1]:.1f}%", (xs[-1], ys[-1]), xytext=(8, 0), textcoords="offset points",
                    va="center", fontsize=8.5, color=INK)
    ax.set_xlabel("compromised RSUs (%)")
    ax.set_ylabel("SFCs poisoned (%)")
    ax.set_xticks(xs)
    ax.set_xlim(-2, 46)
    ax.set_ylim(bottom=0)
    ax.legend(loc="upper left", fontsize=8.5)
    finish(fig, ax, "2_poisoned_vs_attacker_share", "More attackers hurt SPAVM badly; trust stays low",
           f"{N_RSU} RSUs, {N_SLOTS} slots, always-bad attackers, average of {len(SEEDS)} seeds")
    return rows


# 3 --------------------------------------------------------------- attacker types
def graph_attacker_types():
    cases = {"Always-bad": dict(amode="always"), "On-off": dict(amode="onoff"),
             "Stealthy\n(tampers 20%)": dict(amode="always", P_TAMPER=0.2)}
    rows = []
    for label, kw in cases.items():
        for name, mode in list(SCHEMES.items())[:2]:
            r = avg(mode, **kw)
            rows.append({"attacker": label.replace("\n", " "), "scheme": name,
                         "poisoned_%": round(r["poisoned_rate"] * 100, 2),
                         "detect_slot": round(r["avg_detect_slot"], 1) if r["avg_detect_slot"] is not None else ""})
    save_csv("3_attacker_types", rows)
    fig, ax = plt.subplots(figsize=(8, 4.2))
    labels, w = list(cases), 0.36
    for j, name in enumerate(list(SCHEMES)[:2]):
        ys = [r["poisoned_%"] for r in rows if r["scheme"] == name]
        xs = [i + (j - 0.5) * (w + 0.03) for i in range(len(labels))]
        bars = ax.bar(xs, ys, w, color=COLOR[name], label=name, edgecolor=SURFACE, linewidth=2)
        for b, y in zip(bars, ys):
            ax.text(b.get_x() + b.get_width() / 2, y + 0.4, f"{y:.1f}%", ha="center", fontsize=8.5, color=INK)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels)
    ax.set_ylabel("SFCs poisoned (%)")
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper right", fontsize=8.5)
    finish(fig, ax, "3_attacker_types", "Trust works against every attacker type",
           f"{N_RSU} RSUs, 20% compromised, {N_SLOTS} slots, average of {len(SEEDS)} seeds")


# 4 --------------------------------------------------------------- trust trajectories
def graph_trust_trajectories():
    s, _ = run("gate", amode="onoff", seed=2)
    log = s.trust_log
    fig, ax = plt.subplots(figsize=(8, 4.2))
    honest_c, bad_c = "#2a78d6", "#eb6834"
    for r in range(N_RSU):
        bad = s.attacker.is_malicious(r)
        ax.plot(range(len(log)), [row[r] for row in log], "-" if bad else ":",
                color=bad_c if bad else honest_c, lw=2 if bad else 1.2, alpha=1 if bad else 0.7,
                label=("compromised RSU (on-off)" if bad else "honest RSU"))
    for k in range(1, N_SLOTS // config.ONOFF_PERIOD, 2):
        ax.axvspan(k * config.ONOFF_PERIOD, (k + 1) * config.ONOFF_PERIOD, color="#f1efe9", zorder=0)
    ax.axhline(config.TRUST_THETA, color=INK2, lw=1, ls="--")
    ax.text(1, config.TRUST_THETA - 0.05, f"threshold θ = {config.TRUST_THETA}", ha="left", fontsize=8.5, color=INK2)
    h, l = ax.get_legend_handles_labels()
    uniq = dict(zip(l, h))
    ax.legend(uniq.values(), uniq.keys(), loc="lower left", fontsize=8.5)
    ax.set_xlabel("time slot   (shaded = attacker's 'bad' periods)")
    ax.set_ylabel("trust score T")
    ax.set_ylim(0, 1)
    save_csv("4_trust_trajectories", [{"slot": t, **{f"RSU{r}{'_BAD' if s.attacker.is_malicious(r) else ''}": round(v, 3)
                                                      for r, v in enumerate(row)}} for t, row in enumerate(log)])
    finish(fig, ax, "4_trust_trajectories", "Bad RSUs lose trust fast and regain it only slowly",
           "one run (seed 2), on-off attacker: good for 5 slots, bad for 5 slots")


# 5 --------------------------------------------------------------- price of security
def graph_price(rows):
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    xs = sorted({r["attackers_%"] for r in rows})
    for name in SCHEMES:
        d = [r["avg_delay_per_request"] * 1000 for r in rows if r["scheme"] == name]
        a = [r["acceptance"] * 100 for r in rows if r["scheme"] == name]
        axes[0].plot(xs, d, DASH[name], marker=MARK[name], ms=8, color=COLOR[name], lw=2, label=name)
        axes[1].plot(xs, a, DASH[name], marker=MARK[name], ms=8, color=COLOR[name], lw=2, label=name)
    axes[0].set_ylabel("average delay per request (ms)")
    axes[1].set_ylabel("requests accepted (%)")
    axes[0].set_ylim(bottom=0)
    axes[1].set_ylim(80, 100)
    for ax in axes:
        ax.set_xlabel("compromised RSUs (%)")
        ax.set_xticks(xs)
    axes[0].legend(loc="lower left", fontsize=8)
    axes[0].set_title("Delay", loc="left", fontsize=11, fontweight="bold")
    axes[1].set_title("Acceptance", loc="left", fontsize=11, fontweight="bold")
    fig.suptitle("The price of security: at 40% attackers, ~7% more delay and ~2% fewer requests accepted",
                 x=0.01, ha="left", fontsize=12, fontweight="bold")
    fig.tight_layout()
    fig.savefig(f"{OUT}/5_price_of_security.png", dpi=150)
    plt.close(fig)
    print("saved", f"{OUT}/5_price_of_security.png")


# 6 --------------------------------------------------------------- why rho > 1
def graph_rho():
    rhos = [1.0, 2.0, 3.0, 5.0]
    rows = []
    for rh in rhos:
        r = avg("gate", amode="onoff", RHO=rh)
        rows.append({"rho": rh, "poisoned_%": round(r["poisoned_rate"] * 100, 2),
                     "false_block_%": round(r["false_block_share"] * 100, 2)})
    save_csv("6_rho_tradeoff", rows)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    labels = [f"ρ = {int(r)}" for r in rhos]
    for ax, key, title, col in [(axes[0], "poisoned_%", "SFCs poisoned (%)  - lower is safer", "#2a78d6"),
                                (axes[1], "false_block_%", "Honest RSUs wrongly blocked (%)  - lower is fairer", "#2a78d6")]:
        ys = [r[key] for r in rows]
        bars = ax.bar(labels, ys, 0.55, color=col, edgecolor=SURFACE, linewidth=2)
        for b, y in zip(bars, ys):
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
def avg_share(share, **kw):
    """Like avg('gate'), but toggling the Step 5 trust-based sharing limit."""
    amode, frac = kw.pop("amode", "always"), kw.pop("frac", 0.2)
    old = setcfg(**kw)
    res = []
    for sd in SEEDS:
        s = Simulator(N_RSU, N_SLOTS, N_VEH, seed=sd, attack_fraction=frac, attack_mode=amode,
                      trust_mode="gate", share_limit=share)
        r = s.run().summary()
        res.append((r["poisoned_rate"] * 100, r["avg_delay_per_request"] * 1000))
    setcfg(**old)
    return statistics.mean(x[0] for x in res), statistics.mean(x[1] for x in res)


def graph_sharing_limit():
    cases = {"Always-bad": {}, "On-off": {"amode": "onoff"}, "Stealthy": {"P_TAMPER": 0.2},
             "40% attackers": {"frac": 0.4}}
    names = {False: "SPAVM + Trust (ours)", True: "+ trust-based sharing limit"}
    cols = {False: "#2a78d6", True: "#eda100"}
    rows = []
    for label, kw in cases.items():
        for share in (False, True):
            p, d = avg_share(share, **dict(kw))
            rows.append({"attacker": label, "scheme": names[share], "poisoned_%": round(p, 2), "delay_ms": round(d, 1)})
    save_csv("7_sharing_limit", rows)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    labels, w = list(cases), 0.38
    for ax, key, title, fmt in [(axes[0], "poisoned_%", "SFCs poisoned (%)  - lower is safer", "{:.2f}"),
                                (axes[1], "delay_ms", "Average delay per request (ms)", "{:.0f}")]:
        for j, share in enumerate((False, True)):
            ys = [r[key] for r in rows if r["scheme"] == names[share]]
            xs = [i + (j - 0.5) * (w + 0.03) for i in range(len(labels))]
            bars = ax.bar(xs, ys, w, color=cols[share], label=names[share], edgecolor=SURFACE, linewidth=2)
            for b, y in zip(bars, ys):
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


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    graph_over_time()
    frac_rows = graph_vs_fraction()
    graph_attacker_types()
    graph_trust_trajectories()
    graph_price(frac_rows)
    graph_rho()
    graph_sharing_limit()
    print("\n--- Headline (20% compromised, always-bad) ---")
    for r in frac_rows:
        if r["attackers_%"] == 20:
            print(f"{r['scheme']:26s} poisoned={r['poisoned_rate']*100:5.1f}%  delay={r['avg_delay_per_request']*1000:6.1f} ms  "
                  f"accepted={r['acceptance']*100:5.1f}%  honest wrongly blocked={r['false_block_share']*100:4.1f}%")
