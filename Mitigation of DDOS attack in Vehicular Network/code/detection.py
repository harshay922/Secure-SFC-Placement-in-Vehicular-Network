# =====================================================================
# detection.py  -  Layer 1: CB-DRL adjusted-delta detection (no blockchain, no signatures)
# ---------------------------------------------------------------------
# Values are SHARES of capacity in [0, 1]  (0.25 CPU = 24 of 96 cores in use).
# Report of an RSU = what it REALLY uses (orchestrator VNFs + hidden attack).
# L = what the orchestrator ITSELF placed there (its own books).
#
#   Delta = w_cpu*|(cpu - cpu0) - (L_cpu - L_cpu0)| + w_mem*|(mem - mem0) - (L_mem - L_mem0)|
#           (cpu0, mem0, L0 = values at the last ACCEPTED report = the trusted baseline)
#           -> changes the orchestrator caused itself are removed; only UNEXPLAINED change stays
#   phi   = max(phi_min, alpha*sigma + beta*lambda)
#           sigma  = std of the weighted load over the last 20 accepted reports
#           lambda = weighted load of the last accepted report
#   Delta > phi  -> RSU FLAGGED (excluded from placement)
#
# Reports: EVERY RSU reports every 2 s (regular check) + un-flagged RSUs also report before each placement.
# Recovery (our vehicular rule): a flagged RSU's 2-s report is HEALTHY if
#   w_cpu*|cpu - L_cpu| + w_mem*|mem - L_mem| <= phi_min   (its real use matches the orchestrator's books)
#   15 s of healthy reports in a row -> un-flagged.
# =====================================================================

from collections import deque                 # list that keeps only the last N items
import numpy as np                            # std
import config as cfg

HISTORY_MIN = 2                                # need at least 2 accepted reports to compute sigma (warm-up otherwise)
TRUE_ATTACK_SHARE = 0.10                       # SCORING ONLY: an RSU counts as "really attacked" when hidden
                                               # attack load > 10% of its CPU (smallest change the rule can see,
                                               # because phi_min = 0.05 with w_cpu = 0.5 means 10% of CPU)


DET_KEYS = ["attack_episodes", "detection_rate_pct", "detection_delay_s", "flags_total", "false_alarms_per_h",
            "max_flagged_at_once", "avg_flagged_in_window", "report_rounds", "checks"]   # keys of summary()


def weighted(cpu, mem):                        # one number for the load of an RSU
    return cfg.W_CPU * cpu + cfg.W_MEM * mem


class Detector:
    def __init__(self, sim):
        self.sim = sim                                           # the simulation (to read loads)
        self.rsus = list(sim.net.rsus)
        self.report_rounds = 0                                   # how many times RSUs were asked for a report
        self.base = {}                                           # rsu -> (cpu0, mem0, Lcpu0, Lmem0) of last accepted report
        self.hist = {r: deque(maxlen=cfg.SIGMA_WINDOW) for r in self.rsus}   # last 20 accepted weighted loads
        self.flagged = {}                                        # rsu -> second it was flagged
        self.healthy_since = {}                                  # flagged rsu -> second its healthy streak started
        self.events = []                                         # one row per flag (for scoring + csv)
        self.open_event = {}                                     # flagged rsu -> its event row (to fill in unflag_s)
        self.newly_flagged = []                                  # RSUs flagged in the last check (read + emptied by the simulator)
        self.checks = 0                                          # number of checks made
        # ---- scoring only (the detector itself never looks at these) ----
        self.episode_start = {}                                  # rsu -> second a real attack episode started
        self.episodes = []                                       # finished/ongoing episodes: dict(rsu, start, end, detected_s)
        self.flag_timeline = []                                  # (t, number of flagged RSUs)

    # ---------------- what an RSU reports, and what the orchestrator expects ----------------
    def real_share(self, n):                                     # REAL load reported by the RSU
        s = self.sim
        # CPU = CPU DEMAND / capacity (like Linux "load average"): it can go above 1.0 when the RSU is overloaded.
        # (If we cut it at 1.0, a busy RSU that is already near 100% would hide an attack.)
        cpu = (s.used_cpu[n] + s.att_cpu[n]) / s.cap_cpu[n]
        mem = (s.used_mem[n] + s.att_mem[n]) / s.cap_mem[n]
        return cpu, mem

    def legit_share(self, n):                                    # what the orchestrator placed there itself
        s = self.sim
        return s.used_cpu[n] / s.cap_cpu[n], s.used_mem[n] / s.cap_mem[n]

    def phi(self, n):                                            # dynamic threshold, None during warm-up
        h = self.hist[n]
        if len(h) < HISTORY_MIN:
            return None
        lam = h[-1]                                              # load of the last accepted report
        return max(cfg.PHI_MIN, cfg.ALPHA * float(np.std(h)) + cfg.BETA * lam)

    def accept(self, n, cpu, mem, L):                            # report becomes the new trusted baseline
        self.base[n] = (cpu, mem, L[0], L[1])
        self.hist[n].append(weighted(cpu, mem))

    # ---------------- one round of reports ----------------
    def check(self, t, periodic):
        """periodic=True : 2-s timer -> EVERY RSU reports (flagged: recovery check, others: attack check).
           periodic=False: a new request arrived -> only un-flagged RSUs report (attack check before placement)."""
        if periodic:
            who = list(self.rsus)                                # regular check: all 25 RSUs report
        else:
            who = [r for r in self.rsus if r not in self.flagged]
        self.report_rounds += 1
        for n in who:                                            # every reporting RSU sends (cpu, mem) to the orchestrator
            cpu, mem = (round(v, 6) for v in self.real_share(n))
            L = self.legit_share(n)
            if n in self.flagged:                                # ---- recovery check ----
                # strict test: the unexplained load must be below phi_min (not the dynamic phi), otherwise a busy RSU
                # (large sigma) would be un-flagged while attack load is still on it
                healthy = weighted(abs(cpu - L[0]), abs(mem - L[1])) <= cfg.PHI_MIN
                if not healthy:
                    self.healthy_since.pop(n, None)              # streak broken
                    continue
                start = self.healthy_since.setdefault(n, t)      # streak starts (or continues)
                if t - start >= cfg.RECOVERY_HEALTHY_S - cfg.REPORT_INTERVAL_S:   # healthy reports from t0 to t0+13 (about 15 s)
                    del self.flagged[n]; del self.healthy_since[n]
                    self.open_event.pop(n)["unflag_s"] = t       # write the un-flag time into its flag event
                    self.accept(n, cpu, mem, L)                  # clean report = new baseline
                continue
            if n not in self.base:                               # first report ever -> just store it
                self.accept(n, cpu, mem, L); continue
            ph = self.phi(n)
            if ph is None:                                       # warm-up -> accept, no decision
                self.accept(n, cpu, mem, L); continue
            c0, m0, Lc0, Lm0 = self.base[n]
            delta = weighted(abs((cpu - c0) - (L[0] - Lc0)), abs((mem - m0) - (L[1] - Lm0)))   # adjusted delta
            self.checks += 1
            if delta > ph:                                       # unexplained jump -> FLAG
                self.flagged[n] = t
                truth = self.sim.att_cpu[n] / self.sim.cap_cpu[n] > TRUE_ATTACK_SHARE   # scoring only
                ev = {"rsu": n, "flag_s": t, "delta": round(delta, 4), "phi": round(ph, 4),
                      "true_attack": int(truth), "unflag_s": ""}
                self.events.append(ev); self.open_event[n] = ev
                self.newly_flagged.append(n)                     # Step 9: simulator migrates this RSU's VNFs
                for ep in self.episodes:                         # mark the ongoing episode of this RSU as detected
                    if ep["rsu"] == n and ep["end"] is None and ep["detected_s"] is None:
                        ep["detected_s"] = t
            else:
                self.accept(n, cpu, mem, L)                      # normal -> new baseline

    # ---------------- scoring, once per second ----------------
    def tick(self, t):
        for n in self.rsus:
            attacked = self.sim.att_cpu[n] / self.sim.cap_cpu[n] > TRUE_ATTACK_SHARE
            open_ep = next((e for e in self.episodes if e["rsu"] == n and e["end"] is None), None)
            if attacked and open_ep is None:                     # a new real attack episode begins
                self.episodes.append({"rsu": n, "start": t, "end": None,
                                      "detected_s": t if n in self.flagged else None})
            elif not attacked and open_ep is not None:           # episode ends
                open_ep["end"] = t
        self.flag_timeline.append((t, len(self.flagged)))

    def summary(self):
        eps = [e for e in self.episodes if e["end"] is None or e["end"] - e["start"] >= cfg.EPISODE_MIN_S]  # ignore <5 s blips
        det = [e for e in eps if e["detected_s"] is not None]
        delays = [e["detected_s"] - e["start"] for e in det]
        false = [e for e in self.events if not e["true_attack"]]
        hours = cfg.SIM_DURATION_S / 3600
        in_win = [n for t, n in self.flag_timeline if cfg.ATTACK_START_S <= t < cfg.ATTACK_END_S]
        return {
            "attack_episodes": len(eps),
            "detection_rate_pct": len(det) / len(eps) * 100 if eps else 0.0,
            "detection_delay_s": float(np.mean(delays)) if delays else 0.0,
            "flags_total": len(self.events),
            "false_alarms_per_h": len(false) / hours,
            "max_flagged_at_once": max(n for _, n in self.flag_timeline),
            "avg_flagged_in_window": float(np.mean(in_win)) if in_win else 0.0,
            "report_rounds": self.report_rounds,
            "checks": self.checks,
        }
