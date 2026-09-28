KEYS = ("cpu", "mem", "bw")
EPS = 1e-9


class ResourceManager:
    """The ONLY code that changes RSU resource counters (constraints 16-18)."""

    def __init__(self, rsus):
        self.rsus = rsus

    def fits(self, rid, demand):
        r = self.rsus[rid]
        return all(r.used[k] + demand[k] <= r.cap[k] + EPS for k in KEYS)

    def reserve(self, rid, demand):
        assert self.fits(rid, demand), f"reserve would violate capacity on RSU{rid}"
        for k in KEYS:
            self.rsus[rid].used[k] += demand[k]

    def release(self, rid, demand):
        for k in KEYS:
            self.rsus[rid].used[k] -= demand[k]

    def check_invariants(self, containers, tag=""):
        """used == sum of live containers' demand, and used <= capacity, on every RSU."""
        for r in self.rsus:
            exp = {k: 0.0 for k in KEYS}
            for c in containers:
                if c.rsu == r.rid:
                    for k in KEYS:
                        exp[k] += c.vnf.demand()[k]
            for k in KEYS:
                assert abs(r.used[k] - exp[k]) < 1e-6, f"{tag} RSU{r.rid} {k}: leak {r.used[k]} vs {exp[k]}"
                assert r.used[k] <= r.cap[k] + EPS, f"{tag} RSU{r.rid} {k}: over capacity"
