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
# =====================================================================================
# WHAT: This file is the "bad guy" of the simulation. It decides which RSUs
#       (Road Side Units = edge servers by the road) are compromised, and answers
#       simple yes/no questions like "does this RSU tamper with an SFC right now?".
# WHY:  To test a security idea (trust scores) we need attackers to defend against.
#       Default: 20% of RSUs are bad (config.ATTACK_FRACTION = 0.2, a chosen test level;
#       the experiments sweep 0% to 40%). A bad RSU tampers with an SFC passing through
#       its reused container with chance P_TAMPER = 0.8, and ALWAYS lies "I am healthy".
#       Honest RSUs also fail sometimes (P_FAULT = 0.02) - this noise makes the problem
#       realistic: not every failure means "attacker".
#       Attack modes: "always" (bad every slot), "onoff" (good 5 slots, bad 5 slots),
#       "stealthy" (same as always but with a low P_TAMPER, set by the experiments).
# WHO USES IT: spavm/simulator.py creates one Attacker per run and asks it questions
#       while serving SFCs and while sending probes. The controller (trust.py) NEVER
#       reads the "malicious" set directly - only the "oracle" trust mode is allowed to cheat.
# =====================================================================================
import config  # our own settings file (config.py); we read numbers like config.P_TAMPER from it


# "class" defines a new type of object. An Attacker object bundles data (who is bad)
# with functions ("methods") that answer questions about that data.
class Attacker:
    # __init__ is the constructor: Python runs it automatically when we write Attacker(...).
    # "self" is the object being built; every method gets it as the first argument.
    # "fraction=None" is a default value: if the caller does not pass it, it is None.
    # select_rng / event_rng are random number generators (random.Random objects).
    # Two separate ones: select_rng picks WHO is bad, event_rng decides WHEN they misbehave.
    # Keeping them separate means every trust mode sees the SAME bad RSUs for a given seed.
    def __init__(self, num_rsus, select_rng, event_rng, fraction=None, mode=None):
        # "X if condition else Y" is Python's one-line if/else.
        # Here: use the config default when the caller gave nothing, else use the given value.
        fraction = config.ATTACK_FRACTION if fraction is None else fraction
        # self.mode stores the attack mode on the object so other methods can read it later.
        self.mode = config.ATTACK_MODE if mode is None else mode
        # k = how many RSUs are bad. round() gives the nearest whole number (0.2 * 10 = 2).
        k = round(fraction * num_rsus)
        # range(num_rsus) = 0, 1, ..., num_rsus-1 (the RSU ids).
        # rng.sample(seq, k) picks k DIFFERENT ids at random (no repeats).
        # set(...) turns the list into a set: fast "is x in it?" checks.
        # "if k else set()": if k is 0 there are no attackers, so use an empty set.
        self.malicious = set(select_rng.sample(range(num_rsus), k)) if k else set()
        # Keep the event generator; methods below use it to roll dice each time.
        self.rng = event_rng

    # Simple yes/no: is RSU number rid one of the compromised ones?
    def is_malicious(self, rid):
        # "in" checks membership in the set; the result is True or False.
        return rid in self.malicious

    # Being malicious is permanent; "attacking" depends on the mode and the time slot t.
    def attacking(self, rid, t):
        """Is this RSU actively attacking in slot t?"""
        # Honest RSUs never attack. "not in" = the opposite of "in".
        if rid not in self.malicious:
            return False
        # "==" compares two values (a single "=" would be assignment).
        if self.mode == "onoff":
            # "//" is integer division (7 // 5 = 1). "%" is remainder (1 % 2 = 1).
            # t // 5 counts which block of 5 slots we are in: 0,0,0,0,0,1,1,1,1,1,2,...
            # Block number % 2 == 1 means odd blocks -> attack. Even blocks -> behave well.
            return (t // config.ONOFF_PERIOD) % 2 == 1        # good first, then bad
        # Mode "always" (and "stealthy", which is "always" with a low P_TAMPER): attack every slot.
        return True

    # Called once per SFC that passes through a reused container on this RSU.
    def tampers(self, rid, t):
        """Does this RSU's container corrupt one SFC passing through it now?"""
        # rng.random() returns a random float in [0, 1). "< 0.8" is True 80% of the time.
        # "and" short-circuits: if attacking(...) is False, the dice are NOT rolled.
        return self.attacking(rid, t) and self.rng.random() < config.P_TAMPER

    # Honest hardware/software glitches. This is noise, not an attack.
    def honest_fault(self, rid):
        """Benign random failure of an honest RSU (not an attack)."""
        # Only honest RSUs get benign faults here; True about 2% of the time (P_FAULT = 0.02).
        return rid not in self.malicious and self.rng.random() < config.P_FAULT

    # Evidence E1: the controller sends a known test packet and checks the output.
    def probe_fails(self, rid, t):
        """Controller sends a known test packet through this RSU: does output come back wrong?"""
        # "or": the probe fails if the RSU tampers OR it has an honest fault.
        # (An attacker in its "good" phase tampers with nothing, so it passes probes then.)
        return self.tampers(rid, t) or self.honest_fault(rid)

    # What the RSU SAYS about itself. The controller compares this with the probe (evidence E3).
    def self_report_healthy(self, rid, probe_failed):
        """What the RSU CLAIMS about itself. Malicious RSUs always lie ('healthy')."""
        # A compromised RSU always claims "healthy", even when its probe just failed.
        if rid in self.malicious:
            return True
        # "not" flips True/False: probe failed -> report "not healthy"; probe ok -> "healthy".
        return not probe_failed          # honest RSUs report their fault truthfully
