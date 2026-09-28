"""PHASE 1 - STEP 1: Attacker model.

Who is bad?   A fixed fraction of RSUs is compromised (chosen once, per seed).
What do they do?
  * Tamper: a container on a compromised RSU corrupts an SFC passing through it
    with probability P_TAMPER (only while the RSU is in "attack" mode).
  * Lie:    a compromised RSU ALWAYS self-reports "healthy".
Modes:
  * "always": attacks in every slot.
  * "onoff" : behaves well for ONOFF_PERIOD slots, then attacks for ONOFF_PERIOD
              slots, and so on (tries to rebuild trust between attacks).
Honest RSUs are not perfect: they have small random faults (P_FAULT), and they
report those faults truthfully. This noise is what makes trust non-trivial.
"""
import config


class Attacker:
    def __init__(self, num_rsus, select_rng, event_rng, fraction=None, mode=None):
        fraction = config.ATTACK_FRACTION if fraction is None else fraction
        self.mode = config.ATTACK_MODE if mode is None else mode
        k = round(fraction * num_rsus)
        self.malicious = set(select_rng.sample(range(num_rsus), k)) if k else set()
        self.rng = event_rng

    def is_malicious(self, rid):
        return rid in self.malicious

    def attacking(self, rid, t):
        """Is this RSU actively attacking in slot t?"""
        if rid not in self.malicious:
            return False
        if self.mode == "onoff":
            return (t // config.ONOFF_PERIOD) % 2 == 1        # good first, then bad
        return True

    def tampers(self, rid, t):
        """Does this RSU's container corrupt one SFC passing through it now?"""
        return self.attacking(rid, t) and self.rng.random() < config.P_TAMPER

    def honest_fault(self, rid):
        """Benign random failure of an honest RSU (not an attack)."""
        return rid not in self.malicious and self.rng.random() < config.P_FAULT

    def probe_fails(self, rid, t):
        """Controller sends a known test packet through this RSU: does output come back wrong?"""
        return self.tampers(rid, t) or self.honest_fault(rid)

    def self_report_healthy(self, rid, probe_failed):
        """What the RSU CLAIMS about itself. Malicious RSUs always lie ('healthy')."""
        if rid in self.malicious:
            return True
        return not probe_failed          # honest RSUs report their fault truthfully
