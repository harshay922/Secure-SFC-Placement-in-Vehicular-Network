import csv


class Metrics:
    def __init__(self):
        self.rows = []

    def add(self, row):
        self.rows.append(row)

    def summary(self):
        T = lambda k: sum(r[k] for r in self.rows)
        arr, acc = T("arrived"), T("accepted")
        return dict(
            slots=len(self.rows), arrived=arr, accepted=acc,
            acceptance=round(acc / arr, 3) if arr else 0.0,
            cloud_uncovered=T("cloud_uncovered"), cloud_infeasible=T("cloud_infeasible"),
            reuse=T("reuse"), cold=T("cold"),
            reuse_ratio=round(T("reuse") / max(T("reuse") + T("cold"), 1), 3),
            migrations=T("migrations"), deleted=T("deleted"),
            D_hop=round(T("D_hop"), 4),
            D_total=round(T("D_total"), 4),
            avg_delay_per_request=round(T("D_total") / acc, 4) if acc else 0.0,
            R_total=round(T("R_total"), 3),
            final_Q_sum=round(self.rows[-1]["Q_sum"], 3) if self.rows else 0.0,
            # ---- PHASE 1 security ----
            poisoned=T("poisoned"),
            poisoned_rate=round(T("poisoned") / acc, 4) if acc else 0.0,   # share of served SFCs corrupted
            secure_rate=round(1 - T("poisoned") / acc, 4) if acc else 1.0,
            probes=T("probes"), lies_caught=T("lies_caught"), drained=T("drained"),
            # ---- PHASE 2 mobility ----
            honest_net_delay_ms=round(T("honest_net_delay") / T("honest_served") * 1000, 2) if T("honest_served") else 0.0,
            honest_acceptance=round(T("honest_accepted") / T("honest_reqs"), 4) if T("honest_reqs") else 0.0,
            misdirected=T("misdirected"), wasted_cold=T("wasted_cold"),
            corrupt_mig=T("corrupt_mig"),
            corrupt_mig_rate=round(T("corrupt_mig") / T("migrations"), 4) if T("migrations") else 0.0,
            mig_cost=round(T("R_mig"), 3),
            sess_mig_per_slot=round(T("sess_mig") / len(self.rows), 3) if self.rows else 0.0,
            sess_cost_per_slot=round(T("sess_cost") / len(self.rows), 3) if self.rows else 0.0,
            sess_corrupt_rate=round(T("sess_corrupt") / T("sess_mig"), 4) if T("sess_mig") else 0.0,
            honest_access_ms=round(T("sess_access_delay") / T("sess_honest") * 1000, 2) if T("sess_honest") else 0.0,
            liar_flag_rate=round(T("liar_flagged") / T("liar_reports"), 4) if T("liar_reports") else 0.0,
            honest_flag_rate=round(T("honest_flagged") / T("honest_reports"), 4) if T("honest_reports") else 0.0)

    def to_csv(self, path):
        if not self.rows:
            return
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(self.rows[0].keys()))
            w.writeheader()
            w.writerows(self.rows)
