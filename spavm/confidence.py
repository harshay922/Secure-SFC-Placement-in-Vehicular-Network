"""PHASE 2 - STEP 2: Confidence score C for every position report (0 = surely false, 1 = believable).

The controller never trusts a report blindly. For each report it runs three live checks
plus a history term:

  C_signal     RSU that received the message measures its signal strength (RSSI).
               Path-loss model (same exponent THETA as SPAVM eq. 10):
                   RSSI(d) = P0 - 10*THETA*log10(d) + shadowing
               Compare measured RSSI with the RSSI expected at the CLAIMED distance.
               Also: if the claimed position is out of that RSU's radio range, it is
               impossible (VeReMi's "acceptance range threshold" check) -> 0.
  C_neighbours Every other RSU that heard the message does the same comparison, and every
               RSU that SHOULD have heard it (claim is well inside its range) but did not
               counts as a contradiction. Weighted by Phase 1 RSU trust when available.
  C_physics    Is the jump from the previous reported position possible at <= 40 m/s?
               (VeReMi's "simple speed check".)
  T_v          History: the same Beta trust formula as Phase 1, applied to VEHICLES.
               Good evidence = C_now, bad evidence = 1 - C_now, per report.

    C_now = mean(C_signal, C_neighbours, C_physics)
    C     = C_now * (0.5 + 0.5 * T_v)          history can at most halve confidence
"""
import math
import config
from .trust import TrustManager


def rssi_db(d):
    """Relative received power in dB at distance d (the constant P0 cancels in comparisons)."""
    return -10.0 * config.THETA * math.log10(max(d, 1.0))


class ConfidenceEngine:
    def __init__(self, rsus, num_vehicles, rng, rsu_weight=None):
        self.rsus, self.rng = rsus, rng
        self.rsu_weight = rsu_weight or (lambda rid: 1.0)
        self.vtrust = TrustManager(num_vehicles)
        self.prev = {}

    # ---------- physics of the radio (what really happens) ----------
    def hearers(self, true_pos):
        """RSUs that physically receive the message: those within radio range of the TRUE position."""
        out = []
        for r in self.rsus:
            d = math.dist(true_pos, (r.x, r.y))
            if d <= config.COVERAGE_R:
                out.append((r.rid, d))
        return out

    def pick_receiver(self, heard):
        """The RSU whose copy the controller uses: stronger signal = more likely (not always the nearest)."""
        if not heard:
            return None
        w = [1.0 / max(d, 1.0) ** 2 for _, d in heard]
        return self.rng.choices([rid for rid, _ in heard], weights=w)[0]

    # ---------- the confidence score ----------
    def score(self, vid, true_pos, claim, heard, receiver):
        tol2 = 2 * config.P2_RSSI_TOL_DB ** 2
        rx = {rid: d for rid, d in heard}
        measured = {rid: rssi_db(d) + self.rng.gauss(0, config.P2_SHADOW_DB) for rid, d in heard}

        def rsu_score(rid):
            r = self.rsus[rid]
            d_claim = math.dist(claim, (r.x, r.y))
            if d_claim > config.COVERAGE_R:                      # claim says it can't have been heard
                return 0.0
            delta = measured[rid] - rssi_db(d_claim)
            return math.exp(-delta * delta / tol2)

        c_signal = rsu_score(receiver)

        num = den = 0.0
        for r in self.rsus:
            if r.rid == receiver:
                continue
            d_claim = math.dist(claim, (r.x, r.y))
            if r.rid in rx:
                s = rsu_score(r.rid)
            elif d_claim <= 0.9 * config.COVERAGE_R:             # should have heard it, but did not
                s = 0.0
            else:
                continue
            w = self.rsu_weight(r.rid)
            num += w * s
            den += w
        c_nbr = num / den if den > 0 else c_signal

        c_phys = 1.0
        if vid in self.prev:
            speed = math.dist(claim, self.prev[vid]) / config.SLOT_SECONDS
            excess = speed - config.P2_V_MAX
            if excess > 0:
                c_phys = math.exp(-(excess / config.P2_SPEED_TOL) ** 2)
        self.prev[vid] = claim

        c_now = (c_signal + c_nbr + c_phys) / 3.0
        t_v = self.vtrust.T(vid)
        conf = c_now * (0.5 + 0.5 * t_v)
        self.vtrust.add_good(vid, c_now)
        self.vtrust.add_bad(vid, 1.0 - c_now)
        return conf, dict(signal=c_signal, neighbours=c_nbr, physics=c_phys, history=t_v)

    def end_slot(self):
        self.vtrust.end_slot(use_quarantine=False)
