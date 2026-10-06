# WHAT THIS FILE DOES: collects one row of numbers per time slot and, at the end, adds them
#   up into a summary (acceptance, delay, cost, security and mobility results) or a CSV file.
# WHY WE NEED IT: the experiments compare baseline vs Phase 1 vs Phase 2 using these numbers,
#   so all totals and rates are computed in one consistent place.
# WHO CALLS IT: simulator.py calls add(row) every slot; experiment scripts call summary() and to_csv().

import csv                                 # standard library module for reading/writing CSV files


class Metrics:
    # "class" defines a new object type; "self" in the methods is this Metrics object.
    def __init__(self):
        # __init__ runs when Metrics() is created.
        self.rows = []                     # one dict per slot, e.g. {"arrived": 5, "accepted": 4, ...}

    def add(self, row):
        self.rows.append(row)              # store this slot's row at the end of the list

    def summary(self):
        # T is a small helper made with lambda (a one-line unnamed function):
        # T("x") = sum of column "x" over all slots. r[k] reads key k from dict r.
        T = lambda k: sum(r[k] for r in self.rows)
        arr, acc = T("arrived"), T("accepted")   # tuple unpacking: total requests, total accepted
        # dict(name=value, ...) builds a dictionary. Pattern used below:
        # "round(a / b, n) if b else 0.0" = divide only when b is not zero (avoids ZeroDivisionError),
        # and round to n decimal places.
        return dict(
            # ---- baseline SPAVM results ----
            slots=len(self.rows), arrived=arr, accepted=acc,     # number of slots and request counts
            acceptance=round(acc / arr, 3) if arr else 0.0,      # share of requests served at the edge
            cloud_uncovered=T("cloud_uncovered"), cloud_infeasible=T("cloud_infeasible"),   # why requests went to cloud
            reuse=T("reuse"), cold=T("cold"),                    # VNFs served by reuse vs by cold start
            # share of VNFs that reused a container; max(..., 1) avoids dividing by 0
            reuse_ratio=round(T("reuse") / max(T("reuse") + T("cold"), 1), 3),
            migrations=T("migrations"), deleted=T("deleted"),    # VIMA moves; idle containers deleted (eq. 4)
            D_hop=round(T("D_hop"), 4),                          # total hop delay (eq. 11), seconds
            D_total=round(T("D_total"), 4),                      # total delay D (eq. 14), seconds
            avg_delay_per_request=round(T("D_total") / acc, 4) if acc else 0.0,
            R_total=round(T("R_total"), 3),                      # total cost R (eq. 8)
            # self.rows[-1] = last row ([-1] counts from the end): queue debt left at the end (eq. 20)
            final_Q_sum=round(self.rows[-1]["Q_sum"], 3) if self.rows else 0.0,
            # ---- PHASE 1 security ----
            poisoned=T("poisoned"),                              # served SFCs that touched a malicious RSU
            poisoned_rate=round(T("poisoned") / acc, 4) if acc else 0.0,   # share of served SFCs corrupted
            secure_rate=round(1 - T("poisoned") / acc, 4) if acc else 1.0,
            # probes sent to test RSUs, lies the trust module caught, containers drained from quarantined RSUs
            probes=T("probes"), lies_caught=T("lies_caught"), drained=T("drained"),
            # ---- PHASE 2 mobility ----
            # average network delay seen by honest vehicles, converted from seconds to ms (* 1000)
            honest_net_delay_ms=round(T("honest_net_delay") / T("honest_served") * 1000, 2) if T("honest_served") else 0.0,
            honest_acceptance=round(T("honest_accepted") / T("honest_reqs"), 4) if T("honest_reqs") else 0.0,
            # misdirected = sent to an RSU the vehicle cannot reach; wasted_cold = containers started for nothing
            misdirected=T("misdirected"), wasted_cold=T("wasted_cold"),
            corrupt_mig=T("corrupt_mig"),                        # migrations useless under true positions (vima.py)
            corrupt_mig_rate=round(T("corrupt_mig") / T("migrations"), 4) if T("migrations") else 0.0,
            mig_cost=round(T("R_mig"), 3),                       # total migration cost (eq. 6)
            # sess_* = session follow-me migrations (followme.py), averaged per slot
            sess_mig_per_slot=round(T("sess_mig") / len(self.rows), 3) if self.rows else 0.0,
            sess_cost_per_slot=round(T("sess_cost") / len(self.rows), 3) if self.rows else 0.0,
            sess_corrupt_rate=round(T("sess_corrupt") / T("sess_mig"), 4) if T("sess_mig") else 0.0,
            honest_access_ms=round(T("sess_access_delay") / T("sess_honest") * 1000, 2) if T("sess_honest") else 0.0,
            # how often the position checker flagged liars (want high) vs honest vehicles (want low)
            liar_flag_rate=round(T("liar_flagged") / T("liar_reports"), 4) if T("liar_reports") else 0.0,
            honest_flag_rate=round(T("honest_flagged") / T("honest_reports"), 4) if T("honest_reports") else 0.0)

    def to_csv(self, path):
        # Save every slot row to a CSV file (one line per slot) for plotting later.
        if not self.rows:
            return                         # nothing to save
        # "with open(...) as f:" opens the file and closes it automatically at the end of the block.
        # "w" = write mode; newline="" stops blank lines appearing between rows on Windows.
        with open(path, "w", newline="") as f:
            # DictWriter writes dicts as CSV rows; column names come from the first row's keys.
            w = csv.DictWriter(f, fieldnames=list(self.rows[0].keys()))
            w.writeheader()                # first line: column names
            w.writerows(self.rows)         # then one line per slot
