"""PHASE 1 - STEP 2: Trust score per RSU (Beta reputation with forgetting).

For every RSU i we keep two counters:
    a_i = good evidence,  b_i = bad evidence
Each slot:
    a_i <- GAMMA * a_i + good_i
    b_i <- GAMMA * b_i + RHO * bad_i
    T_i = (a_i + 1) / (a_i + b_i + 2)        trust in [0, 1], starts at 0.5
    n_i = a_i + b_i                          how much evidence we have (confidence)

Where does evidence come from? NEVER from what the RSU says about itself.
  E1 probes   : controller tests a random subset of RSUs with known test packets.
  E2 outcomes : end-to-end check of each served SFC.
                success -> small credit to every RSU on the chain
                failure -> blame split over the chain's RSUs, more blame to the
                           less-trusted ones (chain-level blame attribution)
  E3 lies     : RSU says "healthy" but its probe just failed -> LIE_PENALTY.

Why this shape?
  * starts at 0.5      -> a new RSU is "unknown", not trusted, not distrusted
  * GAMMA forgetting   -> recent behaviour matters most (EWMA)
  * RHO > 1            -> slow to gain, fast to lose (defeats on-off attackers)
  * n_i                -> 0.8 from 2 observations != 0.8 from 200 (reused in Phase 2)
"""
import config


class TrustManager:
    def __init__(self, num_rsus):
        self.a = [0.0] * num_rsus
        self.b = [0.0] * num_rsus
        self.quarantined = set()
        self._good = [0.0] * num_rsus
        self._bad = [0.0] * num_rsus
        self.probes_sent = 0
        self.lies_caught = 0

    # ---- reading the score ----
    def T(self, rid):
        return (self.a[rid] + 1.0) / (self.a[rid] + self.b[rid] + 2.0)

    def n(self, rid):
        return self.a[rid] + self.b[rid]

    def allowed(self, rid):
        """Trust gate used by SPVIR and VIMA (Step 3)."""
        if rid in self.quarantined:
            return False
        if self.n(rid) < config.N_MIN:
            return True                  # not enough evidence yet: benefit of the doubt
        return self.T(rid) >= config.TRUST_THETA

    # ---- collecting evidence during a slot ----
    def add_good(self, rid, w=1.0):
        self._good[rid] += w

    def add_bad(self, rid, w=1.0):
        self._bad[rid] += w

    def record_probe(self, rid, failed, claimed_healthy):
        self.probes_sent += 1
        if failed:
            self.add_bad(rid)
            if claimed_healthy:                          # E3: caught lying
                self.add_bad(rid, config.LIE_PENALTY)
                self.lies_caught += 1
        else:
            self.add_good(rid)

    def record_outcome(self, chain_rsus, success):
        """E2: end-to-end result of one SFC. chain_rsus = distinct RSUs it used."""
        if not chain_rsus:
            return
        k = len(chain_rsus)
        if success:
            for r in chain_rsus:
                self.add_good(r, 1.0 / k)
        else:                                            # blame: more to less-trusted RSUs
            w = {r: (1.0 - self.T(r)) + 1e-3 for r in chain_rsus}
            s = sum(w.values())
            for r in chain_rsus:
                self.add_bad(r, w[r] / s)

    # ---- end of slot ----
    def end_slot(self, use_quarantine):
        for i in range(len(self.a)):
            self.a[i] = config.GAMMA * self.a[i] + self._good[i]
            self.b[i] = config.GAMMA * self.b[i] + config.RHO * self._bad[i]
            self._good[i] = self._bad[i] = 0.0
        if use_quarantine:
            for i in range(len(self.a)):
                low = self.n(i) >= config.N_MIN and self.T(i) < config.TRUST_THETA_Q
                if low:
                    self.quarantined.add(i)
                elif i in self.quarantined and self.T(i) >= config.TRUST_THETA:
                    self.quarantined.discard(i)          # recovery if wrongly flagged
