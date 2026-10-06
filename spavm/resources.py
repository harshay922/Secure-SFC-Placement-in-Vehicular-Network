# WHAT THIS FILE DOES: keeps track of how much CPU, memory and bandwidth is used on each RSU,
#   and checks that no RSU ever goes over its capacity.
# WHY WE NEED IT: the paper's constraints 16-18 say used CPU/memory/bandwidth on an RSU must not
#   exceed its capacity. Putting all changes to "used" in ONE class makes bugs (leaks) easy to find.
# WHO USES IT: spavm/simulator.py creates one ResourceManager; SPVIR/VIMA call fits/reserve/release
#   through it when they create, move or delete containers.
KEYS = ("cpu", "mem", "bw")  # tuple of the three resource names (tuple = list that cannot change)
EPS = 1e-9  # tiny tolerance for decimal rounding errors (e.g. 0.1 + 0.2 is not exactly 0.3 in computers)


class ResourceManager:
    """The ONLY code that changes RSU resource counters (constraints 16-18)."""

    def __init__(self, rsus):  # __init__ = constructor, runs when we write ResourceManager(rsus)
        self.rsus = rsus  # store the list of RSU objects on this object (self = this particular object)

    def fits(self, rid, demand):  # True if RSU rid has room for this demand dict
        r = self.rsus[rid]
        # all(...) = True only if the check is True for every k. Checks eq. 16 (cpu), 17 (mem), 18 (bw).
        return all(r.used[k] + demand[k] <= r.cap[k] + EPS for k in KEYS)

    def reserve(self, rid, demand):  # take resources on RSU rid (new container or migration target)
        # assert = stop the program with this message if the condition is False (a safety check).
        assert self.fits(rid, demand), f"reserve would violate capacity on RSU{rid}"
        for k in KEYS:
            self.rsus[rid].used[k] += demand[k]  # add the demand to what is used

    def release(self, rid, demand):  # give back resources (container deleted, or moved away)
        for k in KEYS:
            self.rsus[rid].used[k] -= demand[k]

    def check_invariants(self, containers, tag=""):
        """used == sum of live containers' demand, and used <= capacity, on every RSU."""
        # An "invariant" is a rule that must always be true. This is a debugging check.
        # tag = optional text added to error messages, to say where the check was called.
        for r in self.rsus:
            exp = {k: 0.0 for k in KEYS}  # dict comprehension: expected usage, starting at 0 for each resource
            for c in containers:  # add up the demand of every live container on this RSU
                if c.rsu == r.rid:
                    for k in KEYS:
                        exp[k] += c.vnf.demand()[k]
            for k in KEYS:
                # 1) the counter must match the containers exactly (no resources "lost" or "leaked")
                assert abs(r.used[k] - exp[k]) < 1e-6, f"{tag} RSU{r.rid} {k}: leak {r.used[k]} vs {exp[k]}"
                # 2) constraints 16-18: used must not exceed capacity
                assert r.used[k] <= r.cap[k] + EPS, f"{tag} RSU{r.rid} {k}: over capacity"
