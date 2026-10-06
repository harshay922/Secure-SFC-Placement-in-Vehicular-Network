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
# =====================================================================================
# WHAT: The controller's "memory" about each RSU. For every RSU it keeps a good-evidence
#       counter a and a bad-evidence counter b, and turns them into a trust score T (0..1).
#       It also decides: may this RSU be used (allowed)? should it be quarantined?
# WHY:  SPAVM (the paper) reuses VNF containers on any RSU. If an RSU is compromised,
#       every SFC through it can be tampered with. The trust score lets placement avoid
#       RSUs that have been caught misbehaving - using only evidence the controller
#       collected itself (probes E1, SFC outcomes E2, caught lies E3), never self-reports.
# WHO USES IT: spavm/simulator.py creates one TrustManager per run, feeds it evidence
#       during each slot, and calls end_slot() at the end of each slot. The placement
#       code (SPVIR / VIMA) calls allowed() to skip untrusted RSUs ("gate" mode).
#       phase1_experiments.py plots T over time (graph 4).
#
# KEY SETTINGS (from config.py):
#   GAMMA = 0.9          forgetting: old evidence keeps 90% of its weight each slot
#   RHO = 3              one unit of bad evidence counts 3x a unit of good
#                        ("lose trust 3x faster than you gain it")
#   LIE_PENALTY = 2      extra bad evidence when a failed probe is claimed "healthy"
#   N_MIN = 3            need a+b >= 3 before we believe T (else: benefit of the doubt)
#   TRUST_THETA = 0.6    gate: T below this -> do not place/reuse on this RSU
#   TRUST_THETA_Q = 0.3  quarantine: T below this (with enough evidence) -> banned
#   (PROBE_FRACTION = 0.3 of RSUs are probed per slot; that choice is made in simulator.py)
#
# WORKED EXAMPLE (numbers checked with Python):
#   Start:  a = 0, b = 0              -> T = (0+1)/(0+0+2) = 1/2 = 0.50, n = 0
#   Slot 1: good = 1, bad = 0         -> a = 0.9*0 + 1 = 1.0,  b = 0
#                                        T = (1+1)/(1+0+2) = 2/3 = 0.67, n = 1
#                                        n < N_MIN (3), so allowed() says yes anyway.
#   Slot 2: good = 0, bad = 1         -> a = 0.9*1 = 0.9,  b = 0.9*0 + 3*1 = 3.0
#                                        T = (0.9+1)/(0.9+3+2) = 1.9/5.9 = 0.32, n = 3.9
#                                        n >= 3 and T < 0.6 -> BLOCKED by the gate.
#                                        (T = 0.32 is still above 0.3, so not quarantined.)
#   Slot 3: good = 1, bad = 0         -> a = 0.9*0.9 + 1 = 1.81, b = 0.9*3 = 2.7
#                                        T = 2.81/6.51 = 0.43 -> still blocked.
#                                        One bad slot needs several good slots to undo (RHO).
#   Lie example from a fresh RSU: probe fails AND it claims "healthy":
#       bad = 1 + LIE_PENALTY 2 = 3  ->  b = 3*3 = 9,  T = 1/11 = 0.09  (very low, fast).
# =====================================================================================
import config  # read the tuning numbers (GAMMA, RHO, N_MIN, ...) from config.py


# A class groups the trust data (a, b, ...) and the functions that update and read it.
class TrustManager:
    # Constructor: runs once when simulator.py writes TrustManager(num_rsus).
    def __init__(self, num_rsus):
        # [0.0] * n makes a list of n zeros. self.a[i] is RSU i's good-evidence counter.
        self.a = [0.0] * num_rsus
        # self.b[i] is RSU i's bad-evidence counter. Both start at 0 -> T = 0.5 (unknown).
        self.b = [0.0] * num_rsus
        # set() is an empty set. It holds ids of RSUs banned in "quarantine" mode.
        self.quarantined = set()
        # Evidence collected DURING the current slot. A leading "_" means "internal, not for
        # outside use". It is added into a and b only at end_slot(), so all RSUs update together.
        self._good = [0.0] * num_rsus
        self._bad = [0.0] * num_rsus
        # Simple counters for reporting (how many probes, how many lies caught).
        self.probes_sent = 0
        self.lies_caught = 0

    # ---- reading the score ----
    # T = trust score of RSU rid. "+ 1.0" and "+ 2.0" make a fresh RSU (a=b=0) start at 0.5
    # and stop T from ever being exactly 0 or 1 (this is the mean of a Beta(a+1, b+1) distribution).
    def T(self, rid):
        return (self.a[rid] + 1.0) / (self.a[rid] + self.b[rid] + 2.0)

    # n = total evidence. It tells how much we should believe T.
    def n(self, rid):
        return self.a[rid] + self.b[rid]

    # The gate: may placement put or reuse a VNF on this RSU?
    def allowed(self, rid):
        """Trust gate used by SPVIR and VIMA (Step 3)."""
        # Quarantined RSUs are always refused.
        if rid in self.quarantined:
            return False
        # Too little evidence (a+b < 3): do not punish an RSU we know nothing about.
        if self.n(rid) < config.N_MIN:
            return True                  # not enough evidence yet: benefit of the doubt
        # ">=" means "greater than or equal". Returns True if trusted enough (T >= 0.6).
        return self.T(rid) >= config.TRUST_THETA

    # ---- collecting evidence during a slot ----
    # "w=1.0" is a default weight. "+=" means "add to the current value" (x += w is x = x + w).
    def add_good(self, rid, w=1.0):
        self._good[rid] += w

    # Same for bad evidence. RHO is NOT applied here; it is applied once in end_slot().
    def add_bad(self, rid, w=1.0):
        self._bad[rid] += w

    # Evidence E1 (probe result) and E3 (lie check). Called by the simulator for each probed RSU.
    # failed = did the known test packet come back wrong? claimed_healthy = what the RSU said.
    def record_probe(self, rid, failed, claimed_healthy):
        # Count every probe (for the "probes" overhead number in the results).
        self.probes_sent += 1
        if failed:
            # E1: a failed probe is one unit of bad evidence.
            self.add_bad(rid)
            # E3: it also claimed "healthy" -> it lied. Add LIE_PENALTY (2) more bad evidence.
            # Honest RSUs report faults truthfully, so they never get this penalty.
            if claimed_healthy:                          # E3: caught lying
                self.add_bad(rid, config.LIE_PENALTY)
                self.lies_caught += 1
        # "else" runs when the "if" condition was False: the probe passed -> good evidence.
        else:
            self.add_good(rid)

    # Evidence E2: the end-to-end result of one SFC (did the output come back correct?).
    def record_outcome(self, chain_rsus, success):
        """E2: end-to-end result of one SFC. chain_rsus = distinct RSUs it used."""
        # "not chain_rsus" is True for an empty list/set. No RSUs -> nothing to credit or blame.
        if not chain_rsus:
            # A bare "return" leaves the function early and returns None.
            return
        # len(...) = number of items. k = how many RSUs shared this SFC.
        k = len(chain_rsus)
        if success:
            # "for r in chain_rsus:" loops over each RSU id in the chain, one at a time.
            # Split one unit of credit equally: each RSU gets 1/k.
            for r in chain_rsus:
                self.add_good(r, 1.0 / k)
        # The SFC failed, but we do not know WHICH RSU broke it. Split one unit of blame,
        # giving more to RSUs we already trust less.
        else:                                            # blame: more to less-trusted RSUs
            # This is a "dict comprehension": {key: value for r in ...} builds a dictionary
            # mapping each RSU id r to its blame weight (1 - T) + 0.001.
            # Low T -> big weight. "1e-3" is 0.001 (scientific notation); it keeps every
            # weight above 0 so we never divide by zero even if all T are 1.
            # Example: T = 0.9 and T = 0.5 -> weights 0.101 and 0.501 -> blame 0.17 and 0.83.
            w = {r: (1.0 - self.T(r)) + 1e-3 for r in chain_rsus}
            # .values() gives all the weights; sum(...) adds them. Used to normalise to 1 unit.
            s = sum(w.values())
            for r in chain_rsus:
                # w[r] looks up RSU r's weight in the dictionary. w[r] / s = its share of blame.
                self.add_bad(r, w[r] / s)

    # ---- end of slot ----
    # Called once per slot by the simulator. Folds this slot's evidence into a and b.
    # use_quarantine is True only in the "quarantine" trust mode.
    def end_slot(self, use_quarantine):
        # range(len(self.a)) = 0, 1, ..., number_of_RSUs - 1: visit every RSU.
        for i in range(len(self.a)):
            # Forget a little (keep 90% of old good evidence), then add this slot's good evidence.
            self.a[i] = config.GAMMA * self.a[i] + self._good[i]
            # Same for bad evidence, but multiplied by RHO (3): trust is lost 3x faster.
            self.b[i] = config.GAMMA * self.b[i] + config.RHO * self._bad[i]
            # Chained assignment: set both slot buffers back to 0 for the next slot.
            self._good[i] = self._bad[i] = 0.0
        if use_quarantine:
            for i in range(len(self.a)):
                # "low" is True when we have enough evidence (n >= 3) AND trust is very low (< 0.3).
                low = self.n(i) >= config.N_MIN and self.T(i) < config.TRUST_THETA_Q
                if low:
                    # .add puts i in the set (adding it twice does nothing).
                    self.quarantined.add(i)
                # "elif" = "else if". If a quarantined RSU climbs back to T >= 0.6, release it.
                elif i in self.quarantined and self.T(i) >= config.TRUST_THETA:
                    # .discard removes i from the set (no error if it is not there).
                    self.quarantined.discard(i)          # recovery if wrongly flagged
