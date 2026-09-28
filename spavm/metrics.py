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
            probes=T("probes"), lies_caught=T("lies_caught"), drained=T("drained"))

    def to_csv(self, path):
        if not self.rows:
            return
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(self.rows[0].keys()))
            w.writeheader()
            w.writerows(self.rows)
